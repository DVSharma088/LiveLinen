# issue_material/models.py
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class Issue(models.Model):
    """
    An Issue represents issuing materials for one product/order.
    IssueLines contain the actual inventory items and quantities.
    """
    product = models.CharField(max_length=255)
    order_no = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issues_created",
    )
    created_at = models.DateTimeField(default=timezone.now)
    # Optional audit fields
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Issue #{self.pk} — {self.product} ({self.order_no or 'No order'})"

    # ---- Helpers to read/write stock across different inventory models ----
    @staticmethod
    def _get_stock_attr_name(obj) -> Optional[str]:
        """
        Return the attribute name on the inventory object representing stock, when known.
        Common names checked: 'stock', 'stock_in_mtrs', 'quantity', 'quantity_used'.
        """
        for attr in ("stock", "stock_in_mtrs", "quantity", "quantity_used"):
            if hasattr(obj, attr):
                return attr
        return None

    @staticmethod
    def _read_stock(obj) -> Optional[Decimal]:
        """
        Return current stock as Decimal (or None if not determinable).
        """
        # Prefer explicit method if present
        try:
            if hasattr(obj, "stock"):
                val = getattr(obj, "stock")
            elif hasattr(obj, "stock_in_mtrs"):
                val = getattr(obj, "stock_in_mtrs")
            elif hasattr(obj, "quantity"):
                val = getattr(obj, "quantity")
            elif hasattr(obj, "quantity_used"):
                val = getattr(obj, "quantity_used")
            else:
                # last resort: try numeric attributes
                for attr in dir(obj):
                    if attr.lower().startswith("stock"):
                        val = getattr(obj, attr, None)
                        break
                else:
                    return None
            if val is None:
                return None
            return Decimal(str(val))
        except Exception:
            return None

    @staticmethod
    def _write_stock(obj, new_stock: Decimal):
        """
        Write a new stock value to the inventory object. Prefer existing named fields.
        Caller is responsible for saving the object (obj.save(...)).
        """
        if hasattr(obj, "stock"):
            setattr(obj, "stock", new_stock)
            return "stock"
        if hasattr(obj, "stock_in_mtrs"):
            setattr(obj, "stock_in_mtrs", new_stock)
            return "stock_in_mtrs"
        if hasattr(obj, "quantity"):
            setattr(obj, "quantity", new_stock)
            return "quantity"
        if hasattr(obj, "quantity_used"):
            setattr(obj, "quantity_used", new_stock)
            return "quantity_used"
        # fallback: set attribute 'stock' anyway
        setattr(obj, "stock", new_stock)
        return "stock"

    def apply_issue(self):
        """
        Deduct stock for all IssueLines where from_waste == False.
        Atomic: either all succeed or none. Raises ValidationError if any line would cause negative stock.
        """
        lines = list(self.lines.select_related("content_type").all())
        if not lines:
            return

        # Group lines by content_type so we can lock each model's rows efficiently
        by_ct: Dict[int, List] = {}
        for line in lines:
            if line.content_type_id is None or line.object_id is None:
                raise ValidationError(f"Line {line.pk or '[new]'} missing content_type or object_id.")
            by_ct.setdefault(line.content_type_id, []).append(line)

        with transaction.atomic():
            # For each content type, lock the referenced objects
            locked_instances: Dict[Tuple[int, int], object] = {}  # (ct_id, obj_pk) -> instance
            for ct_id, ct_lines in by_ct.items():
                ct = ContentType.objects.get_for_id(ct_id)
                ModelClass = ct.model_class()
                if ModelClass is None:
                    raise ValidationError(f"ContentType {ct} has no model_class.")
                pks = [l.object_id for l in ct_lines]
                # Lock the rows
                qs = ModelClass.objects.select_for_update().filter(pk__in=pks)
                # Build map
                for inst in qs:
                    locked_instances[(ct_id, inst.pk)] = inst

            # Validation pass: ensure sufficient stock for all non-waste lines
            for line in lines:
                if line.from_waste:
                    # still capture current stock snapshot if possible
                    inv = locked_instances.get((line.content_type_id, line.object_id)) or line.get_inventory_object()
                    line.stock_at_issue = Issue._read_stock(inv)
                    line.save(update_fields=["stock_at_issue"])
                    continue

                inv = locked_instances.get((line.content_type_id, line.object_id))
                if inv is None:
                    raise ValidationError(f"Inventory item not found for line {line.pk or '[new]'}.")

                current_stock = Issue._read_stock(inv)
                if current_stock is None:
                    if hasattr(inv, "reduce_stock"):
                        continue
                    raise ValidationError(f"Cannot determine stock for {inv} (line {line.pk or '[new]'}).")
                try:
                    qty = Decimal(str(line.qty or 0))
                except Exception:
                    raise ValidationError(f"Invalid quantity on line {line.pk or '[new]'}.")

                if current_stock - qty < 0:
                    raise ValidationError(
                        f"Not enough stock for {line.inventory_label()} (available {current_stock}, requested {qty})."
                    )

            # Deduction pass: call model-specific APIs where available, otherwise update numeric field
            modified_instances: Dict[object, List[str]] = {}

            for line in lines:
                inv = locked_instances.get((line.content_type_id, line.object_id))
                if inv is None:
                    inv = line.get_inventory_object()
                    if inv is None:
                        raise ValidationError(f"Inventory item not found for line {line.pk or '[new]'}.")
                qty = Decimal(str(line.qty or 0))
                pre_stock = Issue._read_stock(inv)

                if line.from_waste:
                    line.stock_at_issue = pre_stock
                    line.save(update_fields=["stock_at_issue"])
                    continue

                if hasattr(inv, "reduce_stock") and callable(getattr(inv, "reduce_stock")):
                    inv.reduce_stock(qty)
                    modified_instances.setdefault(inv, [])
                    attr = Issue._get_stock_attr_name(inv) or "stock"
                    modified_instances[inv].append(attr)
                else:
                    current = Issue._read_stock(inv)
                    if current is None:
                        raise ValidationError(f"Cannot update stock for {inv}; unknown stock field.")
                    new = current - qty
                    Issue._write_stock(inv, new)
                    modified_instances.setdefault(inv, []).append(Issue._get_stock_attr_name(inv) or "stock")

                line.stock_at_issue = pre_stock
                line.save(update_fields=["stock_at_issue"])

            # Save all modified inventory instances
            for inst, fields in modified_instances.items():
                uf = list(dict.fromkeys(fields))
                try:
                    inst.save(update_fields=uf + ["updated_at"] if hasattr(inst, "updated_at") else uf)
                except Exception:
                    inst.save()

            # mark applied datetime
            self.applied_at = timezone.now()
            self.save(update_fields=["applied_at"])

    def revert_issue(self):
        """
        Revert (add back) stock for all lines that were actually deducted (from_waste == False).
        """
        lines = list(self.lines.select_related("content_type").all())
        if not lines:
            return

        by_ct: Dict[int, List] = {}
        for line in lines:
            if line.content_type_id is None or line.object_id is None:
                continue
            by_ct.setdefault(line.content_type_id, []).append(line)

        with transaction.atomic():
            locked_instances: Dict[Tuple[int, int], object] = {}
            for ct_id, ct_lines in by_ct.items():
                ct = ContentType.objects.get_for_id(ct_id)
                ModelClass = ct.model_class()
                if ModelClass is None:
                    continue
                pks = [l.object_id for l in ct_lines]
                qs = ModelClass.objects.select_for_update().filter(pk__in=pks)
                for inst in qs:
                    locked_instances[(ct_id, inst.pk)] = inst

            modified_instances: Dict[object, List[str]] = {}
            for line in lines:
                if line.from_waste:
                    continue
                inst = locked_instances.get((line.content_type_id, line.object_id))
                if inst is None:
                    inst = line.get_inventory_object()
                    if inst is None:
                        raise ValidationError(f"Inventory item not found for line {line.pk or '[new]'} during revert.")

                qty = Decimal(str(line.qty or 0))

                if hasattr(inst, "increment_stock") and callable(getattr(inst, "increment_stock")):
                    inst.increment_stock(qty)
                    modified_instances.setdefault(inst, [])
                    attr = Issue._get_stock_attr_name(inst) or "stock"
                    modified_instances[inst].append(attr)
                else:
                    current = Issue._read_stock(inst) or Decimal("0")
                    new = current + qty
                    Issue._write_stock(inst, new)
                    modified_instances.setdefault(inst, []).append(Issue._get_stock_attr_name(inst) or "stock")

            for inst, fields in modified_instances.items():
                uf = list(dict.fromkeys(fields))
                try:
                    inst.save(update_fields=uf + ["updated_at"] if hasattr(inst, "updated_at") else uf)
                except Exception:
                    inst.save()

            self.reverted_at = timezone.now()
            self.save(update_fields=["reverted_at"])


# Optional timestamp fields added to Issue; not required but helpful for auditing
Issue.add_to_class("applied_at", models.DateTimeField(null=True, blank=True))
Issue.add_to_class("reverted_at", models.DateTimeField(null=True, blank=True))


class IssueLine(models.Model):
    """
    Line item for an Issue. Uses GenericForeignKey to point at any inventory model
    (Accessory, Fabric, Printed) in your rawmaterials app.
    """
    INVENTORY_TYPE_ACCESSORY = "accessory"
    INVENTORY_TYPE_FABRIC = "fabric"
    INVENTORY_TYPE_PRINTED = "printed"
    INVENTORY_TYPE_CHOICES = (
        (INVENTORY_TYPE_ACCESSORY, "Accessory"),
        (INVENTORY_TYPE_FABRIC, "Fabric"),
        (INVENTORY_TYPE_PRINTED, "Printed"),
    )

    issue = models.ForeignKey(
        Issue,
        related_name="lines",
        on_delete=models.CASCADE,
    )

    # Inventory type (helps UI and quick filtering)
    inventory_type = models.CharField(max_length=30, choices=INVENTORY_TYPE_CHOICES)

    # GenericForeignKey to point to the actual inventory object
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    inventory_object = GenericForeignKey("content_type", "object_id")

    # snapshot / audit fields
    item_name = models.CharField(max_length=255, blank=True, null=True)
    stock_at_issue = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True
    )

    # new flag: if true, do NOT deduct stock (taken from waste)
    from_waste = models.BooleanField(default=False)

    # quantity to be issued
    qty = models.DecimalField(max_digits=12, decimal_places=3, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        name = self.inventory_label()
        return f"{name} x {self.qty} for Issue#{self.issue_id}"

    def clean(self):
        # Basic validation: inventory_object must exist and qty > 0 (unless from_waste True and qty may be 0?)
        if not self.inventory_object:
            raise ValidationError("Selected inventory item does not exist.")
        try:
            q = Decimal(str(self.qty or 0))
        except Exception:
            raise ValidationError("Quantity must be numeric.")
        if (q or 0) <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        # Optionally ensure inventory_type matches content_type app_label/model (left out for flexibility)

    def inventory_label(self):
        """
        Human-readable label for the referenced inventory object.
        """
        obj = self.get_inventory_object()
        if obj is None:
            return "Unknown item"
        # Try common attributes
        return getattr(obj, "item_name", None) or getattr(obj, "name", None) or getattr(obj, "title", None) or str(obj)

    def get_inventory_object(self):
        """
        Return the actual referenced inventory object (or None).
        """
        return self.inventory_object

    def save(self, *args, **kwargs):
        # Keep item_name cached for audit (helps if inventory item is later renamed/deleted)
        obj = self.get_inventory_object()
        if obj:
            self.item_name = getattr(obj, "item_name", getattr(obj, "name", getattr(obj, "title", str(obj))))
        super().save(*args, **kwargs)


# -------------------------
# Compatibility alias
# -------------------------
# Some parts of your code expect a model named `IssueMaterial`.
# Create a module-level alias so `from .models import IssueMaterial` works.
IssueMaterial = Issue

# Export names explicitly
__all__ = ["Issue", "IssueLine", "IssueMaterial"]
