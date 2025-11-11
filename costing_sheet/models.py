from decimal import Decimal, InvalidOperation
from django.db import models, transaction
from django.utils import timezone
from django.apps import apps
from django.core.exceptions import ValidationError
import re

TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")


def to_decimal(value):
    """Safe conversion to Decimal with fallback to 0."""
    try:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _clean_words(s):
    """Split a string into words (letters/numbers), stripping extra punctuation/spaces."""
    if not s:
        return []
    # Replace non-alphanumeric with spaces, collapse spaces
    s = re.sub(r"[^A-Za-z0-9]+", " ", str(s)).strip()
    if not s:
        return []
    return [w for w in s.split() if w]


def _initials_from_phrase(phrase, max_letters=2):
    """
    Return up to `max_letters` initials from the words of a phrase.
    Example: ("Women Top", 2) -> "WT"; ("Dress", 2) -> "D"
    """
    words = _clean_words(phrase)
    if not words:
        return ""
    initials = "".join(w[0] for w in words[:max_letters])
    return initials.upper()


def _first_n_from_word(word, n=3):
    """First n letters from a single word (letters/numbers only), uppercased."""
    if not word:
        return ""
    w = re.sub(r"[^A-Za-z0-9]", "", str(word))
    return w[:n].upper()


class CostingSheet(models.Model):
    """
    Lean CostingSheet model with optional snapshot link to ComponentMaster and Accessory.

    Extended to store Category Master (new) selection + Size -> Stitch / Finish / Packaging
    snapshot fields so the UI can auto-fill and the values are persisted.

    Now includes auto-generated SKU from (Category, Name, Collection, Color, Size):
      - 1st block (up to 2 chars): initials of Category words (e.g., "Women Top" -> "WT", "Dress" -> "D")
      - 2nd block (up to 2 chars): initials of Collection words (e.g., "Solid Color" -> "SC", "Solid" -> "S")
      - 3rd block (up to 3 chars): first 3 chars of the SECOND word of Name (e.g., "Linen Mate Shoes" -> "MAT",
                                   "Linen White" -> "WHI"; if Name has only one word -> empty)
      - 4th block (up to 2 chars): initials of Color words (e.g., "Angora White" -> "AW", "White" -> "W")
      - 5th block: Size as-is (e.g., "S", "M", "XXL")
      Final SKU is these blocks concatenated without separators.
    """

    category = models.ForeignKey(
        "category_master.CategoryMaster",
        on_delete=models.PROTECT,
        related_name="costing_sheets",
    )

    # Reuse existing size label and optional FK to SizeMaster
    size = models.CharField(max_length=64, blank=True, help_text="Size label (e.g. S, M, L)")
    
    # --- THIS FIELD IS CORRECTED ---
    size_master = models.ForeignKey(
        "category_master_new.CategorySize",  # <-- WAS "size_master.SizeMaster"
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional link to size master entry",
    )

    # Optional link to the newer Category Master (app: category_master_new)
    category_new = models.ForeignKey(
        "category_master_new.Category",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="costing_sheets_new",
        help_text="Optional link to Category Master (New) entry (Name)."
    )

    # Optional human name for the costing row
    name = models.CharField(max_length=255, blank=True)

    # --- NEW: optional fields used by SKU logic ---
    collection = models.CharField(max_length=255, blank=True, help_text="Collection name (e.g., Solid Color)")
    color = models.CharField(max_length=255, blank=True, help_text="Color name (e.g., Angora White)")

    # --- NEW: auto-generated SKU (readable/editable; auto-filled on save if inputs are present) ---
    sku = models.CharField(
        max_length=64,
        blank=True,
        help_text="Auto-generated from Category, Name, Collection, Color, Size"
    )

    # Link to ComponentMaster (Quality Name). Nullable to remain backward-compatible.
    component_master = models.ForeignKey(
        "components.ComponentMaster",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="costing_sheets",
        help_text="Optional link to a Component Master (quality). Values are snapshotted on save.",
    )

    # Plain text fallback label (older code / display)
    component = models.CharField(max_length=255, blank=True, help_text="Component label (from category master)")

    # Snapshot fields copied from ComponentMaster (or editable by user)
    width = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00"),
        help_text="Width (snapshotted from ComponentMaster)."
    )
    width_uom = models.CharField(
        max_length=20, default="inch", blank=True,
        help_text="Unit of measure for width (e.g., 'inch', 'cm')."
    )

    # price per square foot (4 decimal places to match ComponentMaster.precision)
    price_per_sqft = models.DecimalField(
        max_digits=16, decimal_places=4, default=Decimal("0.0000"),
        help_text="Price per square foot (snapshotted from ComponentMaster)."
    )

    # final cost (snapshotted)
    final_cost = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal("0.00"),
        help_text="Final cost snapshot from ComponentMaster (or computed)."
    )

    # --- Accessory fields (existing) ---
    accessory = models.ForeignKey(
        "rawmaterials.Accessory",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="costing_sheets",
        help_text="Optional accessory chosen from inventory (snapshot stored)."
    )
    accessory_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Number of accessory units used for this costing."
    )
    accessory_unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        help_text="Snapshot of accessory price per unit (copied from accessory at save time)."
    )
    accessory_line_total = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"),
        help_text="Snapshot of accessory line total (quantity × unit price)."
    )

    # Fields copied/stored from Category Master (component + percent/price fields)
    gf_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    texas_buying_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    texas_retail_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    shipping_inr = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tx_to_us_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    import_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    new_tariff_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    recip_tariff_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    ship_us_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    us_wholesale = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0.0000"))

    # --- NEW persistent fields requested: Stitch / Finish / Packaging ---
    stitching = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"),
                                    help_text="Snapshot: stitching cost/parameter for selected size.")
    finishing = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"),
                                    help_text="Snapshot: finishing cost/parameter for selected size.")
    packaging = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"),
                                    help_text="Snapshot: packaging cost/parameter for selected size.")

    # --- NEW persistent fields already present in your file (kept) ---
    average = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0.0000"),
                                  help_text="Average (user-entered numeric value).")

    total = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"),
                                help_text="Auto-calculated: Total = Final Cost × Average")

    new_final_price = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"),
                                          help_text="Auto-calculated: Total + Final Cost") # NOTE: Your JS calculates Total + Accessory

    shipping_cost_india = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    shipping_cost_us = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    shipping_cost_europe = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    gf_overhead_cost = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"),
                                           help_text="New Final Price + GF% of New Final Price")

    texas_buying_cost = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    texas_retail = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))

    texas_us_selling_cost = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))

    us_buying_cost_usd = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"),
                                             help_text="Computed US buying cost in USD using tariffs/imports/ship US rules")

    us_wholesale_cost = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"),
                                            help_text="US Wholesale cost (after wholesale % and factor)")

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Costing Sheet"
        verbose_name_plural = "Costing Sheets"

    def __str__(self):
        label = self.name or (str(self.component_master) if self.component_master else f"{self.category}")
        if self.size:
            label = f"{label} — {self.size}"
        return label

    # -------- SKU helpers --------
    def _category_label_for_sku(self):
        """
        Best-effort to get a readable category name for SKU initials.
        Primary: self.category (CategoryMaster)
        Fallbacks: attribute .name/title on category, then str(category).
        """
        try:
            cat = self.category
            if not cat:
                return ""
            for attr in ("name", "title"):
                if hasattr(cat, attr):
                    val = getattr(cat, attr)
                    if val:
                        return str(val)
            return str(cat)
        except Exception:
            return ""

    def _name_second_word_3(self):
        """
        Returns first 3 letters of the SECOND word of Name.
        If Name has only one (or zero) word -> empty.
        """
        words = _clean_words(self.name)
        if len(words) < 2:
            return ""
        return _first_n_from_word(words[1], 3)

    def _compute_sku(self):
        """
        Build SKU by concatenating:
          cat2 + col2 + name2nd3 + color2 + size
        (no separators, uppercase; empty blocks omitted if missing)
        Only generate when all 5 inputs exist (Category, Name, Collection, Color, Size).
        """
        cat_label = self._category_label_for_sku()
        name_val = (self.name or "").strip()
        collection_val = (self.collection or "").strip()
        color_val = (self.color or "").strip()
        size_val = (self.size or "").strip()

        # Must have all inputs
        if not (cat_label and name_val and collection_val and color_val and size_val):
            return ""

        cat2 = _initials_from_phrase(cat_label, max_letters=2)              # e.g., "WT" or "D"
        col2 = _initials_from_phrase(collection_val, max_letters=2)         # e.g., "SC" or "S"
        name2nd3 = self._name_second_word_3()                               # e.g., "MAT" or "WHI" or ""
        color2 = _initials_from_phrase(color_val, max_letters=2)            # e.g., "AW" or "W"
        size_block = re.sub(r"\s+", "", size_val).upper()                    # "S", "M", "XXL"

        parts = [cat2, col2, name2nd3, color2, size_block]
        sku = "".join(p for p in parts if p)  # concat non-empty blocks
        return sku

    # --- existing helper methods for copying from category/component/accessory (kept as-is) ---
    def _get_preferred_category_model(self):
        try:
            return apps.get_model("category_master", "CategoryMaster")
        except LookupError:
            try:
                return apps.get_model("category_master_new", "Category")
            except LookupError:
                return None

    def _copy_from_category_if_missing(self):
        CatModel = self._get_preferred_category_model()
        if not CatModel:
            return
        try:
            cat = CatModel.objects.filter(pk=self.category_id).first()
        except Exception:
            cat = None
        if not cat:
            return

        def _get_attr_from_cat(cat_obj, attr):
            try:
                val = getattr(cat_obj, attr)
                if hasattr(val, "__class__") and not isinstance(val, (str, bytes, int, float, Decimal)):
                    for n in ("name", "title", "component_name"):
                        if hasattr(val, n):
                            try:
                                v2 = getattr(val, n)
                                if v2 is not None:
                                    return v2
                            except Exception:
                                continue
                    try:
                        return str(val)
                    except Exception:
                        return None
                return val
            except Exception:
                return None

        def _copy(field_name, cat_attr_candidates, decimal=False):
            current = getattr(self, field_name, None)
            empty_decimal = (current is None) or (decimal and to_decimal(current) == Decimal("0"))
            empty_str = (current is None) or (str(current).strip() == "")
            should_copy = empty_decimal if decimal else empty_str
            if not should_copy:
                return

            for attr in cat_attr_candidates:
                val = _get_attr_from_cat(cat, attr)
                if val is None:
                    continue
                try:
                    if decimal:
                        val_decimal = to_decimal(val)
                        if val_decimal != Decimal("0"):
                            setattr(self, field_name, val_decimal)
                            return
                    else:
                        sval = str(val).strip()
                        if sval != "":
                            setattr(self, field_name, sval)
                            return
                except Exception:
                    continue

        _copy("component", ("component", "component_id", "component_name", "name", "title"), decimal=False)
        _copy("gf_percent", ("gf_overhead", "gf_percent", "gf", "gross_factory_percent"), decimal=True)
        _copy("texas_buying_percent", ("texas_buying_cost", "texas_buying_percent", "texas_buying", "tx_buying_percent"), decimal=True)
        _copy("texas_retail_percent", ("texas_retail", "texas_retail_percent", "tx_retail_percent"), decimal=True)
        _copy("shipping_inr", ("shipping_cost_inr", "shipping_inr", "shipping", "ship_inr"), decimal=True)
        _copy("tx_to_us_percent", ("texas_to_us_selling_cost", "tx_to_us_percent", "tx_to_us", "tx_to_us_pct"), decimal=True)
        _copy("import_percent", ("import_cost", "import_percent", "import_pct", "import_duty_percent"), decimal=True)
        _copy("new_tariff_percent", ("new_tariff", "new_tariff_percent", "tariff_percent"), decimal=True)
        _copy("recip_tariff_percent", ("reciprocal_tariff", "reciprocal_tariff_percent", "recip_tariff_percent"), decimal=True)
        _copy("ship_us_percent", ("shipping_us", "ship_us_percent", "ship_us"), decimal=True)
        _copy("us_wholesale", ("us_wholesale_margin", "us_wholesale_percent", "us_wholesale_price", "us_wholesale_value"), decimal=True)

    def _copy_from_component_master_if_missing(self):
        if not self.component_master:
            return

        cm = self.component_master

        def set_if_empty(field_name, val, decimal_places=None):
            try:
                current = getattr(self, field_name, None)
                if isinstance(current, Decimal):
                    empty = (to_decimal(current) == Decimal("0"))
                else:
                    empty = (current is None) or (str(current).strip() == "")

                if empty:
                    if val is None:
                        return
                    if isinstance(val, Decimal):
                        if decimal_places == 4:
                            setattr(self, field_name, val.quantize(FOURPLACES))
                        else:
                            setattr(self, field_name, val.quantize(TWOPLACES))
                    else:
                        if field_name in ("width", "price_per_sqft", "final_cost"):
                            try:
                                d = to_decimal(val)
                                if decimal_places == 4:
                                    setattr(self, field_name, d.quantize(FOURPLACES))
                                else:
                                    setattr(self, field_name, d.quantize(TWOPLACES))
                            except Exception:
                                setattr(self, field_name, val)
                        else:
                            setattr(self, field_name, val)
            except Exception:
                pass

        try:
            set_if_empty("width", to_decimal(getattr(cm, "width", None)))
            if not (self.width_uom and str(self.width_uom).strip()):
                self.width_uom = getattr(cm, "width_uom", "inch") or "inch"
        except Exception:
            pass

        try:
            set_if_empty("price_per_sqft", to_decimal(getattr(cm, "price_per_sqfoot", None)), decimal_places=4)
        except Exception:
            pass

        try:
            set_if_empty("final_cost", to_decimal(getattr(cm, "final_cost", None)))
        except Exception:
            pass

        try:
            if not (self.component and str(self.component).strip()):
                try:
                    display_label = str(cm)
                    if display_label and str(display_label).strip():
                        self.component = display_label
                except Exception:
                    pass
        except Exception:
            pass

    def _copy_accessory_snapshot_if_missing(self):
        if not self.accessory:
            return

        try:
            acc_model = apps.get_model("rawmaterials", "Accessory")
        except LookupError:
            acc_model = None

        try:
            acc = None
            if acc_model and hasattr(self.accessory, "unit_cost") and isinstance(self.accessory, acc_model):
                acc = self.accessory

            if not acc and acc_model:
                try:
                    acc = acc_model.objects.filter(pk=self.accessory_id).first()
                except Exception:
                    acc = None

            unit_price = None
            if acc:
                unit_price = getattr(acc, "unit_cost", None) or getattr(acc, "cost_per_unit", None)

            try:
                current = getattr(self, "accessory_unit_price", None)
                if current is None or to_decimal(current) == Decimal("0"):
                    if unit_price is not None:
                        self.accessory_unit_price = to_decimal(unit_price).quantize(TWOPLACES)
            except Exception:
                pass

            try:
                qty = int(getattr(self, "accessory_quantity", 0) or 0)
            except Exception:
                qty = 0

            try:
                up = to_decimal(getattr(self, "accessory_unit_price", Decimal("0.00")))
                line = (up * Decimal(qty)).quantize(TWOPLACES)
                self.accessory_line_total = line
            except Exception:
                try:
                    if self.accessory_line_total in (None, ""):
                        self.accessory_line_total = Decimal("0.00")
                except Exception:
                    self.accessory_line_total = Decimal("0.00")
        except Exception:
            pass

    def apply_accessory_stock_reduction(self, reduce=True):
        if not self.accessory or not self.accessory_quantity:
            return

        try:
            Accessory = apps.get_model("rawmaterials", "Accessory")
        except LookupError:
            raise ValidationError("Accessory model not available.")

        acc = Accessory.objects.select_for_update().filter(pk=self.accessory_id).first()
        if not acc:
            raise ValidationError("Accessory not found.")

        qty = int(self.accessory_quantity or 0)
        if qty <= 0:
            raise ValidationError("Accessory quantity must be positive to reduce stock.")

        with transaction.atomic():
            acc.reduce_stock(qty)
            acc.save(update_fields=["stock", "updated_at"])

    # --- New helper: try to copy Stitch/Finish/Packaging from Category New or SizeMaster ---
    def _copy_sfp_from_category_new_if_missing(self):
        """
        Populate stitching/finishing/packaging from:
         - category_new related sizes if available (preferred),
         - fallback to size_master attributes if present,
         - best-effort parsing of category labels.

        The code is defensive because we don't know exact third-party model shapes.
        """
        # If values already set (non-zero) don't overwrite
        try:
            if to_decimal(self.stitching) != Decimal("0") or to_decimal(self.finishing) != Decimal("0") or to_decimal(self.packaging) != Decimal("0"):
                return
        except Exception:
            pass

        # Helper to set S/F/P only if current is zero/empty
        def set_if_empty_decimal(field_name, val):
            try:
                cur = getattr(self, field_name, None)
                if cur in (None, "") or to_decimal(cur) == Decimal("0"):
                    if val is None:
                        return
                    d = to_decimal(val)
                    setattr(self, field_name, d.quantize(TWOPLACES))
            except Exception:
                pass
        
        # --- NEW STRATEGY: Use the size_master_id which points to CategorySize ---
        size_obj = None
        if self.size_master_id:
            try:
                CategorySize = apps.get_model("category_master_new", "CategorySize")
                size_obj = CategorySize.objects.filter(pk=self.size_master_id).first()
            except Exception:
                size_obj = None
        
        if size_obj:
            try:
                stitch_val = getattr(size_obj, "stitching", None) or getattr(size_obj, "stitching_cost", None)
                finish_val = getattr(size_obj, "finishing", None) or getattr(size_obj, "finishing_cost", None)
                pack_val = getattr(size_obj, "packaging", None) or getattr(size_obj, "packaging_cost", None)

                set_if_empty_decimal("stitching", stitch_val)
                set_if_empty_decimal("finishing", finish_val)
                set_if_empty_decimal("packaging", pack_val)
                
                # Also ensure the 'size' label field is snapshotted
                if not (self.size and self.size.strip()):
                    size_label = getattr(size_obj, "name", None) or getattr(size_obj, "size", None) or str(size_obj.id)
                    self.size = size_label
                    
                return # Found and set, so we are done
            except Exception:
                pass # Fallback

        # 1) Try category_new -> sizes relationship (LEGACY FALLBACK)
        try:
            cat = None
            if self.category_new_id:
                try:
                    CategoryNew = apps.get_model("category_master_new", "Category")
                    cat = CategoryNew.objects.filter(pk=self.category_new_id).first()
                except Exception:
                    cat = None

            if cat:
                # Common patterns: cat.sizes (related name), cat.size_set, cat.sizes_all, cat.size_list
                candidate_lists = []
                for attr in ("sizes", "size_set", "size_list", "sizes_all", "size_master_set"):
                    if hasattr(cat, attr):
                        try:
                            candidate = getattr(cat, attr)
                            # if it's a manager/queryset, evaluate
                            if hasattr(candidate, "all"):
                                candidate_lists.append(candidate.all())
                            else:
                                candidate_lists.append(candidate)
                        except Exception:
                            continue

                # If nothing found, also try to inspect direct attribute 'sizes_data' or 'sizes_json'
                if not candidate_lists:
                    for alt in ("sizes_data", "sizes_json", "size_data"):
                        if hasattr(cat, alt):
                            try:
                                candidate = getattr(cat, alt)
                                candidate_lists.append(candidate)
                            except Exception:
                                continue

                # Now search through candidate lists for a matching size label
                size_label = (self.size or "").strip()
                found = None
                for cl in candidate_lists:
                    try:
                        for item in cl:
                            # item may be a model instance or a dict-like
                            s_label = None
                            try:
                                # model-like
                                s_label = getattr(item, "size", None) or getattr(item, "label", None) or getattr(item, "name", None)
                            except Exception:
                                s_label = None

                            if s_label is None and isinstance(item, dict):
                                s_label = item.get("size") or item.get("label") or item.get("name")

                            if s_label is None:
                                # try string conversion
                                try:
                                    s_label = str(item)
                                except Exception:
                                    s_label = None

                            if s_label and str(s_label).strip() == size_label:
                                found = item
                                break
                        if found:
                            break
                    except Exception:
                        continue

                if found:
                    # extract stitch/finish/pack from found item
                    stitch_val = None
                    finish_val = None
                    pack_val = None
                    try:
                        stitch_val = getattr(found, "stitch", None) or getattr(found, "stitching", None) or getattr(found, "stitching_cost", None) or (found.get("stitch") if isinstance(found, dict) else None)
                    except Exception:
                        stitch_val = None
                    try:
                        finish_val = getattr(found, "finish", None) or getattr(found, "finishing", None) or getattr(found, "finish_cost", None) or (found.get("finish") if isinstance(found, dict) else None)
                    except Exception:
                        finish_val = None
                    try:
                        pack_val = getattr(found, "pack", None) or getattr(found, "packaging", None) or getattr(found, "pack_cost", None) or (found.get("pack") if isinstance(found, dict) else None)
                    except Exception:
                        pack_val = None

                    set_if_empty_decimal("stitching", stitch_val)
                    set_if_empty_decimal("finishing", finish_val)
                    set_if_empty_decimal("packaging", pack_val)
                    # If we've set anything, return early
                    if to_decimal(getattr(self, "stitching")) != Decimal("0") or to_decimal(getattr(self, "finishing")) != Decimal("0") or to_decimal(getattr(self, "packaging")) != Decimal("0"):
                        return
        except Exception:
            # swallow errors: fallback below
            pass


        # 3) Best-effort: try to parse numbers embedded in the size label (e.g., "S — 100.00 / 100.00 / 100.00")
        try:
            txt = (self.size or "") or ""
            m = re.search(r"([\d\.]+)\s*\/\s*([\d\.]+)\s*\/\s*([\d\.]+)", txt)
            if m:
                try:
                    set_if_empty_decimal("stitching", m.group(1))
                    set_if_empty_decimal("finishing", m.group(2))
                    set_if_empty_decimal("packaging", m.group(3))
                except Exception:
                    pass
        except Exception:
            pass

    def _compute_additional_costs(self):
        """
        Compute the requested derived fields (Total, New Final Price, GF Overhead,
        Texas Buying Cost, Texas Retail, Texas US Selling Cost, US Buying Cost (USD),
        US Wholesale Cost).
        """
        def pct(v):
            return (to_decimal(v) / Decimal("100")) if v is not None else Decimal("0")

        final_cost = to_decimal(self.final_cost)
        avg = to_decimal(self.average)

        total = (final_cost * avg).quantize(FOURPLACES)
        self.total = total

        # --- THIS CALCULATION IS BASED ON YOUR JS ---
        # new_final_price = Total + Accessory Line Total
        new_final_price = (total + to_decimal(self.accessory_line_total)).quantize(FOURPLACES)
        self.new_final_price = new_final_price

        gf_multiplier = Decimal("1") + pct(self.gf_percent)
        gf_overhead_cost = (new_final_price * gf_multiplier).quantize(FOURPLACES)
        self.gf_overhead_cost = gf_overhead_cost

        texas_buying_multiplier = Decimal("1") + pct(self.texas_buying_percent)
        texas_buying_cost = (gf_overhead_cost * texas_buying_multiplier).quantize(FOURPLACES)
        self.texas_buying_cost = texas_buying_cost

        texas_retail_multiplier = Decimal("1") + pct(self.texas_retail_percent)
        # --- THIS CALCULATION IS BASED ON YOUR JS ---
        # texas_retail = (Texas Buying * Texas Retail %) + Shipping (INR)
        shipping_inr = to_decimal(self.shipping_cost_india) or to_decimal(self.shipping_inr) # Use explicit field first
        texas_retail = (texas_buying_cost * texas_retail_multiplier) + shipping_inr
        texas_retail = texas_retail.quantize(FOURPLACES)
        self.texas_retail = texas_retail

        tx_to_us_multiplier = Decimal("1") + pct(self.tx_to_us_percent)
        texas_us_selling_cost = (texas_buying_cost * tx_to_us_multiplier).quantize(FOURPLACES)
        self.texas_us_selling_cost = texas_us_selling_cost

        import_mult = Decimal("1") + pct(self.import_percent)
        new_tariff_mult = Decimal("1") + pct(self.new_tariff_percent)
        recip_tariff_mult = Decimal("1") + pct(self.recip_tariff_percent)
        ship_us_mult = Decimal("1") + pct(self.ship_us_percent)

        try:
            part_a = (texas_us_selling_cost * import_mult * new_tariff_mult * recip_tariff_mult).quantize(FOURPLACES)
        except Exception:
            part_a = Decimal("0")

        try:
            # --- THIS CALCULATION IS BASED ON YOUR JS ---
            part_b = (texas_us_selling_cost * ship_us_mult) / Decimal("80.0")
        except Exception:
            part_b = Decimal("0")

        us_buying = (part_a + part_b).quantize(FOURPLACES)
        self.us_buying_cost_usd = us_buying

        try:
            # --- THIS CALCULATION IS BASED ON YOUR JS ---
            us_wholesale_multiplier = Decimal("1") + pct(self.us_wholesale)
            us_wholesale_cost = (us_buying * us_wholesale_multiplier) / Decimal("0.85")
            self.us_wholesale_cost = us_wholesale_cost.quantize(FOURPLACES)
        except Exception:
            self.us_wholesale_cost = Decimal("0")

    def save(self, *args, **kwargs):
        # Attempt to copy values from the linked category if current fields are empty
        try:
            self._copy_from_category_if_missing()
        except Exception:
            pass

        # Snapshot values from linked ComponentMaster if present and fields empty
        try:
            self._copy_from_component_master_if_missing()
        except Exception:
            pass

        # Snapshot accessory price/line total if accessory set
        try:
            self._copy_accessory_snapshot_if_missing()
        except Exception:
            pass

        # Snapshot Stitch/Finish/Packaging from Category New / SizeMaster if missing
        try:
            self._copy_sfp_from_category_new_if_missing()
        except Exception:
            pass

        # Ensure numeric defaults are sane
        try:
            if self.width in (None, ""):
                self.width = Decimal("0.00")
        except Exception:
            self.width = Decimal("0.00")

        try:
            if self.price_per_sqft in (None, ""):
                self.price_per_sqft = Decimal("0.0000")
        except Exception:
            self.price_per_sqft = Decimal("0.0000")

        try:
            if self.final_cost in (None, ""):
                self.final_cost = Decimal("0.00")
        except Exception:
            self.final_cost = Decimal("0.00")

        # accessory numeric defaults
        try:
            if self.accessory_unit_price in (None, ""):
                self.accessory_unit_price = Decimal("0.00")
        except Exception:
            self.accessory_unit_price = Decimal("0.00")

        try:
            if self.accessory_line_total in (None, ""):
                self.accessory_line_total = Decimal("0.00")
        except Exception:
            self.accessory_line_total = Decimal("0.00")

        # ensure average exists
        try:
            if self.average in (None, ""):
                self.average = Decimal("0.0000")
        except Exception:
            self.average = Decimal("0.0000")

        # shipping user-entered defaults
        try:
            if self.shipping_cost_india in (None, ""):
                self.shipping_cost_india = Decimal("0.00")
        except Exception:
            self.shipping_cost_india = Decimal("0.00")

        try:
            if self.shipping_cost_us in (None, ""):
                self.shipping_cost_us = Decimal("0.00")
        except Exception:
            self.shipping_cost_us = Decimal("0.00")

        try:
            if self.shipping_cost_europe in (None, ""):
                self.shipping_cost_europe = Decimal("0.00")
        except Exception:
            self.shipping_cost_europe = Decimal("0.00")

        # stitching/finishing/packaging defaults
        try:
            if self.stitching in (None, ""):
                self.stitching = Decimal("0.00")
        except Exception:
            self.stitching = Decimal("0.00")

        try:
            if self.finishing in (None, ""):
                self.finishing = Decimal("0.00")
        except Exception:
            self.finishing = Decimal("0.00")

        try:
            if self.packaging in (None, ""):
                self.packaging = Decimal("0.00")
        except Exception:
            self.packaging = Decimal("0.00")

        # compute additional derived fields (best-effort; safe against missing decimals)
        try:
            self._compute_additional_costs()
        except Exception:
            # swallow computation errors to avoid blocking save
            pass

        # --- Auto-generate SKU if inputs are present and sku is empty OR whitespace ---
        try:
            if not (self.sku and str(self.sku).strip()):
                computed = self._compute_sku()
                if computed:
                    self.sku = computed
        except Exception:
            # do not block save if SKU computation fails
            pass

        super().save(*args, **kwargs)