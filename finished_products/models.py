import re
from decimal import Decimal, ROUND_HALF_UP
from django.db import models, transaction
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.core.exceptions import ValidationError
from django.utils import timezone

# Import CostComponent to apply overheads / wastage / fixed costs
from components.models import CostComponent


# -------------------------
# Choices
# -------------------------
PRODUCT_NAME_CHOICES = (
    ('Adrian', 'Adrian'),
    ('Aiden', 'Aiden'),
    ('Arthur', 'Arthur'),
    ('Aster', 'Aster'),
    ('Aurelia', 'Aurelia'),
    ('Brandon', 'Brandon'),
    ('Bray', 'Bray'),
    ('Britney', 'Britney'),
    ('Bruce', 'Bruce'),
    ('Caprice', 'Caprice'),
    ('Cassendra', 'Cassendra'),
    ('Cavira', 'Cavira'),
    ('Citrene', 'Citrene'),
    ('Citrus', 'Citrus'),
    ('Clark', 'Clark'),
    ('Dakota', 'Dakota'),
    ('Danica', 'Danica'),
    ('Della', 'Della'),
    ('Delphine', 'Delphine'),
    ('Dove', 'Dove'),
    ('Dusk', 'Dusk'),
    ('Edwina', 'Edwina'),
    ('Elsa', 'Elsa'),
    ('George', 'George'),
    ('Giselle', 'Giselle'),
    ('Glory', 'Glory'),
    ('Harbor', 'Harbor'),
    ('Heather', 'Heather'),
    ('Ivanka', 'Ivanka'),
    ('Julian', 'Julian'),
    ('Kira', 'Kira'),
    ('Lavinia', 'Lavinia'),
    ('Luna', 'Luna'),
    ('Magnolia', 'Magnolia'),
    ('Malcom', 'Malcom'),
    ('Marianne', 'Marianne'),
    ('Mistera', 'Mistera'),
    ('Moana', 'Moana'),
    ('Moira', 'Moira'),
    ('Nerina', 'Nerina'),
    ('Nolan', 'Nolan'),
    ('Penelope', 'Penelope'),
    ('Peter', 'Peter'),
    ('Philip', 'Philip'),
    ('Rivana', 'Rivana'),
    ('Rosaline', 'Rosaline'),
    ('Rose', 'Rose'),
    ('Sandrine', 'Sandrine'),
    ('Selah', 'Selah'),
    ('Serena', 'Serena'),
    ('Sheryl', 'Sheryl'),
    ('Silas', 'Silas'),
    ('Simon', 'Simon'),
    ('Tansy', 'Tansy'),
    ('Theo', 'Theo'),
    ('Virelle', 'Virelle'),
    ('Walter', 'Walter'),
    ('Yuna', 'Yuna'),
    ('Yuri', 'Yuri'),
)

PRODUCT_TYPE_CHOICES = (
    ("Men's Loungewear", "Men's Loungewear"),
    ("Men's Pant", "Men's Pant"),
    ("Men's Shirt", "Men's Shirt"),
    ("Men's Short", "Men's Short"),
    ("Women's Co-Ord Set", "Women's Co-Ord Set"),
    ("Women's Dress", "Women's Dress"),
    ("Women's Pant", "Women's Pant"),
    ("Women's Shirt", "Women's Shirt"),
    ("Women's Skirt", "Women's Skirt"),
    ("Women's Top", "Women's Top"),
)

COLLECTION_CHOICES = (
    ('Bridging Threads', 'Bridging Threads'),
    ('Capsule Collection', 'Capsule Collection'),
    ('Drifted Folklore', 'Drifted Folklore'),
    ('Ember Bloom', 'Ember Bloom'),
    ('Hand Work', 'Hand Work'),
    ('Hand Work & Machine Embroidery', 'Hand Work & Machine Embroidery'),
    ('Lace', 'Lace'),
    ('Machine Embroidery', 'Machine Embroidery'),
    ('Serenity Calls', 'Serenity Calls'),
    ('Solid', 'Solid'),
    ('Stripe', 'Stripe'),
    ('Whimsical Elements', 'Whimsical Elements'),
)

COLOR_CHOICES = (
    ('Wild Wind', 'Wild Wind'),
    ('Olive Mist', 'Olive Mist'),
    ('Rose Wood', 'Rose Wood'),
    ('Muted Lime', 'Muted Lime'),
    ('Sage Green', 'Sage Green'),
    ('Pacific Blue', 'Pacific Blue'),
    ('Midnight Green', 'Midnight Green'),
    ('Brown Bean', 'Brown Bean'),
    ('Muted Mocha', 'Muted Mocha'),
    ('Angora White', 'Angora White'),
    ('Petal Pink', 'Petal Pink'),
    ('Denim Chambray', 'Denim Chambray'),
    ('Teal Chambray', 'Teal Chambray'),
    ('Amber Chambray', 'Amber Chambray'),
    ('Burl Wood', 'Burl Wood'),
    ('Indigo Blue', 'Indigo Blue'),
    ('Crushed Violet', 'Crushed Violet'),
    ('Clay Caffiene & Petal Pink', 'Clay Caffiene & Petal Pink'),
    ('Misty Lilac, Cinnamon Swept, Oatmeal & Charcoal Drift', 'Misty Lilac, Cinnamon Swept, Oatmeal & Charcoal Drift'),
    ('Crushed Violet & Clay Caffiene', 'Crushed Violet & Clay Caffiene'),
    ('Angora White & Oatmeal', 'Angora White & Oatmeal'),
    ('Angora White & Moody Blue', 'Angora White & Moody Blue'),
    ('Oatmeal & Sage Green', 'Oatmeal & Sage Green'),
    ('Muted Momcha & Petal Pink', 'Muted Momcha & Petal Pink'),
    ('Misty Lilac (Removed Embroidery Of Dove)', 'Misty Lilac (Removed Embroidery Of Dove)'),
    ('Angora White (Removed Embroidery Of Dove)', 'Angora White (Removed Embroidery Of Dove)'),
    ('Charcoal Drift, Wild Wind (Removed Embroidery Of Rosaline)', 'Charcoal Drift, Wild Wind (Removed Embroidery Of Rosaline)'),
    ('Misty Lilac', 'Misty Lilac'),
    ('Wild Wind & Oatmeal (Removed Embroidery Of Mistera)', 'Wild Wind & Oatmeal (Removed Embroidery Of Mistera)'),
    ('Burl Wood & Oatmeal (Removed Embroidery Of Cassendra)', 'Burl Wood & Oatmeal (Removed Embroidery Of Cassendra)'),
    ('Olive Mist & Wild Wind (Removed Embroidery Of Aurelia)', 'Olive Mist & Wild Wind (Removed Embroidery Of Aurelia)'),
    ('Olive Mist & Muted Mocha (Removed Embroidery Of Serena)', 'Olive Mist & Muted Mocha (Removed Embroidery Of Serena)'),
    ('Charcoal Drift & Wild Wind (Removed Embroidery Of Heather)', 'Charcoal Drift & Wild Wind (Removed Embroidery Of Heather)'),
    ('Sage Green & Angora White (Removed Embroidery Of Virelle)', 'Sage Green & Angora White (Removed Embroidery Of Virelle)'),
    ('Misty Lilac & Olive Mist (Removed Embroidery Of Cavira)', 'Misty Lilac & Olive Mist (Removed Embroidery Of Cavira)'),
    ('Olive Mist & Pacific Blue (Removed Embroidery Of Lavinia)', 'Olive Mist & Pacific Blue (Removed Embroidery Of Lavinia)'),
    ('Pacific Blue & Burl Wood (Removed Embroidery Of Nerina)', 'Pacific Blue & Burl Wood (Removed Embroidery Of Nerina)'),
    ('Charcoal Drift & Olive Mist (Removed Embroidery Of Tansy)', 'Charcoal Drift & Olive Mist (Removed Embroidery Of Tansy)'),
    ('Petal Pink, Midnight Green & Muted Lime', 'Petal Pink, Midnight Green & Muted Lime'),
    ('Muted Momcha, Stormy Blue & Rose Wood', 'Muted Momcha, Stormy Blue & Rose Wood'),
    ('Burl Wood, Berry Blush & Summer Yellow', 'Burl Wood, Berry Blush & Summer Yellow'),
    ('Wild Wind, Oatmeat, Petal Pink', 'Wild Wind, Oatmeat, Petal Pink'),
    ('Olive Mist, Oatmeal & Berry Blush', 'Olive Mist, Oatmeal & Berry Blush'),
    ('Rose Wood, Oatmeal & Sage Green', 'Rose Wood, Oatmeal & Sage Green'),
    ('Muted Lime, Angora White, Petal Pink & Stormy Blue', 'Muted Lime, Angora White, Petal Pink & Stormy Blue'),
    ('Sunburnt Yellow', 'Sunburnt Yellow'),
    ('Angora White & Indigo Blue', 'Angora White & Indigo Blue'),
    ('Sage Green, Misty Lilac & Clay Caffiene', 'Sage Green, Misty Lilac & Clay Caffiene'),
    ('Rusty Ochre', 'Rusty Ochre'),
    ('Summer Yellow', 'Summer Yellow'),
    ('Charcoal Drift', 'Charcoal Drift'),
    ('Muted Mocha & Mud Brown', 'Muted Mocha & Mud Brown'),
    ('Angora White & Charcoal Drift', 'Angora White & Charcoal Drift'),
    ('Burl Wood & Angora White', 'Burl Wood & Angora White'),
    ('Midnight Green, Sage Green & Wild Wild', 'Midnight Green, Sage Green & Wild Wild'),
    ('Sage Green & Misty Lilac', 'Sage Green & Misty Lilac'),
    ('Rose Wood & Olive Mist', 'Rose Wood & Olive Mist'),
    ('Muted Lime, Berry Blush & Bottle Green', 'Muted Lime, Berry Blush & Bottle Green'),
    ('Midnight Green & Olive Mist', 'Midnight Green & Olive Mist'),
    ('Angora White & Burl Wood', 'Angora White & Burl Wood'),
    ('Muted Lime & Pacific Blue', 'Muted Lime & Pacific Blue'),
    ('Midnigt Green', 'Midnigt Green'),
    ('Olive Mist & Muted Mocha', 'Olive Mist & Muted Mocha'),
    ('Wild Wind & Charcoal Drift', 'Wild Wind & Charcoal Drift'),
    ('Rose Wood & Wild Wind', 'Rose Wood & Wild Wind'),
    ('Sage Green & Midnight Green', 'Sage Green & Midnight Green'),
    ('Oatmeal & Burl Wood', 'Oatmeal & Burl Wood'),
    ('Angora White (Removed Embroidery Of Elsa)', 'Angora White (Removed Embroidery Of Elsa)'),
    ('Misty Lilac & Sage Green', 'Misty Lilac & Sage Green'),
    ('Charcoal Drift, Muted Mocha & Midnight Green', 'Charcoal Drift, Muted Mocha & Midnight Green'),
    ('Angora White, Muted Mocha & Sunburnt Yellow', 'Angora White, Muted Mocha & Sunburnt Yellow'),
    ('Brown Bean & Sage Green', 'Brown Bean & Sage Green'),
    ('Wild Wind, Brown Bean & Petl Pink', 'Wild Wind, Brown Bean & Petl Pink'),
    ('Olive Mist, Midnight Green & Pacific Blue', 'Olive Mist, Midnight Green & Pacific Blue'),
    ('Clay Caffiene & Brown Bean', 'Clay Caffiene & Brown Bean'),
    ('Wild Wind, Midnight Green, Purple Sunset, Oatmeal', 'Wild Wind, Midnight Green, Purple Sunset, Oatmeal'),
    ('Berry Blush', 'Berry Blush'),
    ('Angora White & Olive Mist', 'Angora White & Olive Mist'),
    ('Mud Brown', 'Mud Brown'),
    ('Swirly Green', 'Swirly Green'),
    ('Swirly Red', 'Swirly Red'),
    ('Swirly Yellow', 'Swirly Yellow'),
    ('Vern Green', 'Vern Green'),
    ('Vern Yellow', 'Vern Yellow'),
    ('Tiffany Green', 'Tiffany Green'),
    ('Tiffany Blue', 'Tiffany Blue'),
    ('Vern Red', 'Vern Red'),
    ('Rene Green', 'Rene Green'),
    ('Rene Red', 'Rene Red'),
)

SIZE_CHOICES = (
    ('1', '1'),
    ('2', '2'),
    ('3', '3'),
    ('4', '4'),
)


# -------------------------
# Helper functions for SKU parts
# -------------------------
def _first_n_alpha(value: str, n: int) -> str:
    """Return first n alphabetical characters uppercased, pad with X if needed."""
    if not value:
        return 'X' * n
    letters = re.findall(r'[A-Za-z]', value)
    out = ''.join(letters[:n]).upper()
    if len(out) < n:
        out = out.ljust(n, 'X')
    return out


def _two_initials_or_first_two(value: str) -> str:
    """
    Produce a 2-character code:
    - If value has multiple words, return initials of first two words (e.g. 'Rose Wood' -> 'RW').
    - If single word, return first two alphabetic characters (e.g. 'Olive' -> 'OL').
    - Pad with X if needed.
    """
    if not value:
        return 'XX'
    words = re.findall(r"[A-Za-z]+", value)
    if len(words) >= 2:
        initials = (words[0][0] + words[1][0]).upper()
        return initials
    # single word: use first two letters
    return _first_n_alpha(value, 2)


def _three_letters(value: str) -> str:
    """Return first three alphabetical chars uppercase, padded with X if needed."""
    return _first_n_alpha(value, 3)


# simple audit for stock movements
class StockMovement(models.Model):
    """
    Record stock changes for traceability.
    Stores a generic relation to the material object (Accessory/Fabric/Printed...).
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    material = GenericForeignKey('content_type', 'object_id')

    qty_change = models.DecimalField(max_digits=14, decimal_places=3)  # negative = deduction
    reason = models.CharField(max_length=200)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.material} {self.qty_change} on {self.created_at:%Y-%m-%d %H:%M}"


class FinishedProduct(models.Model):
    """
    FinishedProduct with dropdown choices for Product Name, Product Type, Collection, Color and Size.
    SKU pattern now:
      SKU = first2(Product Type) + first2(Collection) + first3(Product Name) + first2(Color) + Size
    Example: Product Type="Women's Dress" -> WD
             Collection="Ember Bloom" -> EB
             Name="Nerina" -> NER
             Color="Rose Wood" -> RW
             Size=1 -> 1
    SKU => WDEBNERRW1  (but code uses uppercase and pads if needed)
    """
    name = models.CharField(max_length=255, choices=PRODUCT_NAME_CHOICES)
    product_type = models.CharField(max_length=64, choices=PRODUCT_TYPE_CHOICES, blank=True)
    fabric_collection = models.CharField(max_length=128, choices=COLLECTION_CHOICES, blank=True)
    fabric_color_name = models.CharField(max_length=255, choices=COLOR_CHOICES, blank=True)

    # keep sku in DB but generate it automatically; no need for UI input
    sku = models.CharField(max_length=100, blank=True, null=True, unique=True)

    size = models.CharField(max_length=2, choices=SIZE_CHOICES, blank=True, null=True)
    average = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    fabric_quality = models.CharField(max_length=255, blank=True)
    fabric_width = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    product_category = models.CharField(max_length=255, blank=True)
    fabric_pattern = models.CharField(max_length=255, blank=True)

    product_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    total_manufacturing_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.sku:
            return f"{self.name} ({self.sku})"
        return self.name

    def _generate_sku_base(self) -> str:
        """
        Build the SKU from the new pattern:
        product_type (2) + collection (2) + product_name (3) + color (2) + size (1)
        """
        part_pt = _two_initials_or_first_two(self.product_type)
        part_coll = _two_initials_or_first_two(self.fabric_collection)
        part_name = _three_letters(self.name)
        part_color = _two_initials_or_first_two(self.fabric_color_name)
        part_size = (self.size or '')
        return f"{part_pt}{part_coll}{part_name}{part_color}{part_size}"

    def _ensure_unique_sku(self, base_sku: str) -> str:
        """
        Ensure SKU uniqueness. If base_sku already exists for another object,
        append -1, -2, ... until unique.
        """
        candidate = base_sku
        suffix = 0
        while True:
            qs = FinishedProduct.objects.filter(sku=candidate)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if not qs.exists():
                return candidate
            suffix += 1
            candidate = f"{base_sku}-{suffix}"

    def save(self, *args, **kwargs):
        """
        Generate SKU automatically if not present or when designed auto pattern should regenerate.
        """
        regenerate = False
        auto_base = self._generate_sku_base().upper()

        if not self.sku:
            regenerate = True
        else:
            # If existing SKU does not follow the auto base prefix, do not overwrite custom SKU.
            if not self.sku.upper().startswith(auto_base):
                regenerate = False
            else:
                # If the SKU currently uses the auto-base and fields changed, regenerate.
                if not self.sku.upper().startswith(auto_base):
                    regenerate = True

        if regenerate:
            base = auto_base
            unique_sku = self._ensure_unique_sku(base)
            self.sku = unique_sku

        super().save(*args, **kwargs)

    def compute_total_cost(self):
        total = Decimal('0.00')
        for line in self.lines.all():
            total += (line.line_cost or Decimal('0.00'))
        return total

    def _apply_cost_components(self, raw_total: Decimal) -> (Decimal, list):
        added = Decimal('0.00')
        details = []

        comps = CostComponent.objects.filter(is_active=True).order_by('name')
        for comp in comps:
            contrib = comp.apply_to_base(raw_total)
            contrib = contrib.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if contrib != Decimal('0.00'):
                details.append((comp.name, contrib))
            added += contrib

        added = added.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return added, details

    def process_deduction(self, reason="Manufacturing - Finished Product creation"):
        if not self.pk:
            raise ValidationError("FinishedProduct must be saved before processing deductions.")

        with transaction.atomic():
            raw_total = Decimal('0.00')

            for line in self.lines.select_related():
                material = line.material
                if material is None:
                    raise ValidationError(f"Line {line.pk or ''} has no material selected.")

                mat_model = material.__class__
                try:
                    mat_locked = mat_model.objects.select_for_update().get(pk=material.pk)
                except mat_model.DoesNotExist:
                    raise ValidationError(f"Material no longer exists for line {line.pk}.")

                try:
                    qty = Decimal(line.qty_per_unit or Decimal('0.000'))
                except Exception:
                    raise ValidationError(f"Invalid quantity on line {line.pk}.")

                try:
                    new_stock_value = mat_locked.reduce_stock(qty)
                except ValidationError as e:
                    raise ValidationError(f"Insufficient stock or invalid qty for material {mat_locked}: {e}")

                saved_obj = None
                if hasattr(mat_locked, 'stock'):
                    mat_locked.save(update_fields=['stock'])
                    saved_obj = mat_locked
                elif hasattr(mat_locked, 'fabric') and hasattr(getattr(mat_locked, 'fabric'), 'stock'):
                    mat_locked.fabric.save(update_fields=['stock', 'updated_at'])
                    saved_obj = mat_locked.fabric
                else:
                    mat_locked.save()
                    saved_obj = mat_locked

                StockMovement.objects.create(
                    content_type=ContentType.objects.get_for_model(saved_obj),
                    object_id=saved_obj.pk,
                    qty_change=-(qty or Decimal('0.000')),
                    reason=f"{reason} - finished product: {self.name}"
                )

                unit_cost = getattr(mat_locked, 'unit_cost', None) or getattr(mat_locked, 'rate', None) or Decimal('0.00')
                line_cost = (unit_cost or Decimal('0.00')) * (qty or Decimal('0.000'))

                if line.line_cost != line_cost:
                    line.line_cost = line_cost
                    line.save(update_fields=['line_cost'])

                raw_total += line_cost

            added_from_components, comp_details = self._apply_cost_components(raw_total)
            grand_total = (raw_total + added_from_components).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            self.total_manufacturing_cost = grand_total
            self.save(update_fields=['total_manufacturing_cost'])

            return {
                "raw_total": raw_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                "components_added": added_from_components,
                "components_detail": comp_details,
                "grand_total": grand_total,
            }


class FinishedProductLine(models.Model):
    product = models.ForeignKey(FinishedProduct, related_name='lines', on_delete=models.CASCADE)

    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveIntegerField()
    material = GenericForeignKey('content_type', 'object_id')

    qty_per_unit = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal('0.000'))
    line_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    def calculate_line_cost(self):
        unit_cost = getattr(self.material, 'unit_cost', None) or getattr(self.material, 'rate', None) or Decimal('0.00')
        return (unit_cost or Decimal('0.00')) * (self.qty_per_unit or Decimal('0.00'))

    def save(self, *args, **kwargs):
        self.line_cost = self.calculate_line_cost()
        super().save(*args, **kwargs)
