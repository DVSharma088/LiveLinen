from decimal import Decimal, InvalidOperation
import csv
import io
import re

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.db.models.deletion import ProtectedError
from django.db import transaction
from django.http import HttpResponse
from django.apps import apps

# Import models and forms used by the app.
from .models import Fabric, Accessory, Printed
from .forms import FabricForm, AccessoryForm, PrintedForm, CSVUploadForm

# import Vendor to allow creating/resolving vendors on the fly
from vendors.models import Vendor


# ----------------- role helpers (local to this module) -----------------
def _in_group(user, group_name):
    return user.groups.filter(name=group_name).exists()


def is_admin(user):
    """Admin = superuser OR group 'Admin'."""
    return user.is_superuser or _in_group(user, "Admin")


def is_manager(user):
    """Manager membership (managers implicitly count as employees)."""
    return _in_group(user, "Manager") or is_admin(user)


def is_employee(user):
    """Employee membership: explicit Employee group or managers/admins."""
    return _in_group(user, "Employee") or is_manager(user)


def can_manage_inventory(user):
    """
    Per your spec: Admin, Manager and Employee can view/create inventory and manage items.
    We treat 'manage' here as create/edit operations.
    """
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["Admin", "Manager", "Employee"]).exists()


def can_delete_inventory(user):
    """
    Who may delete inventory items?
    - Admin and Manager can delete.
    """
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=["Admin", "Manager"]).exists()


# -------------------------
# Helpers for defensive rendering
# -------------------------
def _coerce_decimal_or_none(value):
    """Convert to Decimal for safe rendering."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _parse_decimal(value, default=None, required=False):
    """
    Helper to parse a Decimal from cleaned strings/numbers. Returns Decimal or default.
    If required=True and parsing fails or value is blank -> raises ValueError.
    This expects 'value' to be already cleaned text or numeric; it will remove commas used as thousands separators.
    """
    if value in (None, ""):
        if required:
            raise ValueError("Missing required numeric value.")
        return default
    try:
        txt = str(value).strip()
        # treat single-character placeholders as missing
        if txt in ("-", "—", "–"):
            if required:
                raise ValueError("Missing required numeric value.")
            return default
        txt = txt.replace(",", "")  # remove thousands separators
        return Decimal(txt)
    except (InvalidOperation, TypeError, ValueError) as e:
        raise ValueError(f"Invalid numeric value '{value}'.") from e


def _parse_int(value, default=None, required=False):
    """Parse int-like values; allow numeric strings"""
    if value in (None, ""):
        if required:
            raise ValueError("Missing required integer value.")
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"Invalid integer value '{value}'.")


# -------------------------
# Vendor helper: resolve or create (returns None when vendor text is missing)
# -------------------------
def _get_or_create_vendor(vendor_val):
    """
    Resolve vendor_val into a Vendor instance.
    - If vendor_val is None/empty -> returns None
    - If vendor_val is integer-like -> try Vendor by pk
    - Otherwise try lookup by vendor_name (case-insensitive)
    - If not found, create a new Vendor with vendor_name=vendor_val (trimmed) and return it.
    """
    if vendor_val in (None, ""):
        return None

    v_raw = str(vendor_val).strip()
    if v_raw == "":
        return None

    # try id
    try:
        vid = int(v_raw)
        vendor = Vendor.objects.filter(pk=vid).first()
        if vendor:
            return vendor
    except Exception:
        pass

    # try name lookup (case-insensitive)
    vendor = Vendor.objects.filter(vendor_name__iexact=v_raw).first()
    if vendor:
        return vendor

    # create new vendor (uses get_or_create to avoid duplicates)
    vendor, created = Vendor.objects.get_or_create(
        vendor_name=v_raw,
        defaults={"rate": Decimal("0.00")}
    )
    return vendor


# -------------------------
# CSV helper
# -------------------------
def _queryset_to_csv_response(queryset, field_getters, filename):
    """
    Build an HttpResponse with CSV content.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    # header
    headers = [col for col, _ in field_getters]
    writer.writerow(headers)

    # rows
    for obj in queryset:
        row = []
        for _, getter in field_getters:
            try:
                val = getter(obj)
            except Exception:
                val = ""
            # Ensure no problems with Decimal or None
            if isinstance(val, Decimal):
                val = str(val)
            if val is None:
                val = ""
            row.append(val)
        writer.writerow(row)

    resp = HttpResponse(buffer.getvalue(), content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# ------------------------------
# Inventory list / overview
# ------------------------------
@login_required
def inventory_list(request):
    """
    Unified inventory page. Renders partials for accessories, fabrics, and printeds.
    Query param 'type' can be 'accessory', 'fabric', 'printed' or omitted for 'all'.
    """
    qtype = (request.GET.get("type") or "").lower()
    active_type = "all" if qtype not in ("accessory", "fabric", "printed") else qtype

    accessories = Accessory.objects.select_related("vendor").all().order_by("-id")
    fabrics = Fabric.objects.select_related("vendor").all().order_by("-id")
    printeds = Printed.objects.select_related("fabric", "fabric__vendor", "vendor").all().order_by("-id")

    can_edit = can_manage_inventory(request.user)
    can_create = can_manage_inventory(request.user)
    can_delete = can_delete_inventory(request.user)

    # quality is a CharField now — don't coerce it to Decimal here
    accessory_numeric_fields = ("width", "stock", "cost_per_unit")
    fabric_numeric_fields = ("fabric_width", "cost_per_unit")
    printed_numeric_fields = ("cost_per_unit", "width")

    for acc in accessories:
        for field in accessory_numeric_fields:
            if hasattr(acc, field):
                raw = getattr(acc, field)
                setattr(acc, field, _coerce_decimal_or_none(raw))

    for f in fabrics:
        for field in fabric_numeric_fields:
            if hasattr(f, field):
                raw = getattr(f, field)
                setattr(f, field, _coerce_decimal_or_none(raw))

    for p in printeds:
        for field in printed_numeric_fields:
            if hasattr(p, field):
                raw = getattr(p, field)
                setattr(p, field, _coerce_decimal_or_none(raw))

    context = {
        "accessories": accessories,
        "fabrics": fabrics,
        "printeds": printeds,
        "active_type": active_type,
        "can_edit": can_edit,
        "can_create": can_create,
        "can_delete": can_delete,
    }
    return render(request, "rawmaterials/inventory_list.html", context)


# ------------------------------
# CSV download views
# ------------------------------
@login_required
@user_passes_test(is_employee)
def accessory_download_csv(request):
    """
    Export accessories with full columns that match the form/importer:
    id, name, quality, base_color, type, width, use_in, stock, cost_per_unit, vendor
    """
    qs = Accessory.objects.select_related("vendor").all().order_by("id")

    def vendor_name(obj):
        v = getattr(obj, "vendor", None)
        if v is None:
            return ""
        return getattr(v, "vendor_name", None) or getattr(v, "name", None) or str(v)

    # Note: Accessory uses 'item_type' in model; map it to header 'type' for CSV compatibility
    field_getters = [
        ("id", lambda o: getattr(o, "id", "")),
        ("name", lambda o: getattr(o, "item_name", "") or getattr(o, "name", "") or getattr(o, "product", "")),
        ("quality", lambda o: getattr(o, "quality", "") or getattr(o, "quality_text", "")),
        ("base_color", lambda o: getattr(o, "base_color", "")),
        ("type", lambda o: getattr(o, "item_type", "") or getattr(o, "type", "")),
        ("width", lambda o: getattr(o, "width", "") or ""),
        ("use_in", lambda o: getattr(o, "use_in", "")),
        ("stock", lambda o: getattr(o, "stock", "")),
        ("cost_per_unit", lambda o: getattr(o, "cost_per_unit", "")),
        ("vendor", vendor_name),
    ]

    return _queryset_to_csv_response(qs, field_getters, "accessories.csv")


@login_required
@user_passes_test(is_employee)
def fabric_download_csv(request):
    qs = Fabric.objects.select_related("vendor").all().order_by("id")

    def vendor_name(obj):
        v = getattr(obj, "vendor", None)
        if v is None:
            return ""
        return getattr(v, "vendor_name", None) or getattr(v, "name", None) or str(v)

    field_getters = [
        ("id", lambda o: getattr(o, "id", "")),
        ("item_name", lambda o: getattr(o, "item_name", "") or getattr(o, "name", "") or getattr(o, "product", "")),
        ("fabric_width", lambda o: getattr(o, "fabric_width", "") or getattr(o, "width", "")),
        ("quality", lambda o: getattr(o, "quality", "")),
        ("stock", lambda o: getattr(o, "stock_in_mtrs", "")),
        ("cost_per_unit", lambda o: getattr(o, "cost_per_unit", "")),
        ("base_color", lambda o: getattr(o, "base_color", "")),
        ("type", lambda o: getattr(o, "type", "") or getattr(o, "product_type", "")),
        ("use_in", lambda o: getattr(o, "use_in", "")),
        ("vendor", vendor_name),
    ]

    return _queryset_to_csv_response(qs, field_getters, "fabrics.csv")


@login_required
@user_passes_test(is_employee)
def printed_download_csv(request):
    """
    Export printed items with columns matching printed list / form:
    Product, Fabric (item_name), Quality, Base Color, Type, Width, Use In,
    Unit, Quantity Used, Stock, Cost Per Unit, Rate, Vendor
    """
    qs = Printed.objects.select_related("fabric", "fabric__vendor", "vendor").all().order_by("id")

    def vendor_name(obj):
        v = getattr(obj, "vendor", None)
        if v is None:
            # try fabric vendor if printed vendor missing
            f = getattr(obj, "fabric", None)
            if f:
                fv = getattr(f, "vendor", None)
                if fv:
                    return getattr(fv, "vendor_name", None) or getattr(fv, "name", None) or str(fv)
            return ""
        return getattr(v, "vendor_name", None) or getattr(v, "name", None) or str(v)

    def fabric_ref(obj):
        f = getattr(obj, "fabric", None)
        if not f:
            return ""
        return getattr(f, "item_name", None) or getattr(f, "name", None) or str(f)

    def fabric_id(obj):
        f = getattr(obj, "fabric", None)
        if not f:
            return ""
        return getattr(f, "id", "")

    def _unit_for(obj):
        # prefer printed.unit, fallback to fabric.unit if present; return empty string if none
        u = getattr(obj, "unit", None)
        if u:
            return u
        f = getattr(obj, "fabric", None)
        if f:
            fu = getattr(f, "unit", None)
            if fu:
                return fu
        return ""

    field_getters = [
        ("product", lambda o: getattr(o, "product", "") or getattr(o, "name", "") or getattr(o, "item_name", "")),
        ("fabric_item_name", fabric_ref),
        ("quality", lambda o: getattr(o, "quality", "") or (getattr(o, "fabric", None) and getattr(o.fabric, "quality", "")) or ""),
        ("base_color", lambda o: getattr(o, "base_color", "") or (getattr(o, "fabric", None) and getattr(o.fabric, "base_color", "")) or ""),
        ("product_type", lambda o: getattr(o, "product_type", "") or getattr(o, "type", "") or (getattr(o, "fabric", None) and getattr(o.fabric, "type", "")) or ""),
        ("width", lambda o: getattr(o, "width", "") or (getattr(o, "fabric", None) and getattr(o.fabric, "fabric_width", "")) or ""),
        ("use_in", lambda o: getattr(o, "use_in", "") or (getattr(o, "fabric", None) and getattr(o.fabric, "use_in", "")) or ""),
        ("unit", _unit_for),
        ("quantity_used", lambda o: getattr(o, "quantity_used", "")),
        ("stock", lambda o: getattr(o, "stock", "") or getattr(getattr(o, "fabric", None), "stock_in_mtrs", "") or ""),
        ("cost_per_unit", lambda o: getattr(o, "cost_per_unit", "") or (getattr(o, "fabric", None) and getattr(o.fabric, "cost_per_unit", "")) or ""),
        ("rate", lambda o: getattr(o, "rate", "")),
        ("vendor", vendor_name),
    ]

    return _queryset_to_csv_response(qs, field_getters, "printeds.csv")


# ------------------------------
# CSV upload / import view (fixed header sets; first row is header)
# ------------------------------
@login_required
@user_passes_test(can_manage_inventory)
def upload_inventory_csv(request):
    """
    Upload CSV and create/update Inventory rows.
    Improved cleaning of input cells (preserve em-dash when part of real data; treat single-character placeholders as missing).
    """
    if request.method != "POST":
        form = CSVUploadForm()
        return render(request, "rawmaterials/upload_csv.html", {"form": form})

    form = CSVUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Upload form invalid. Please attach a CSV file and choose a target.")
        return redirect(reverse("rawmaterials:inventory"))

    csv_file = form.cleaned_data["csv_file"]
    target = form.cleaned_data["target"]

    # --- read text safely and handle BOM ---
    try:
        text = csv_file.read().decode("utf-8-sig")
    except AttributeError:
        try:
            data = csv_file.read()
            if isinstance(data, bytes):
                text = data.decode("utf-8-sig")
            else:
                text = str(data)
        except Exception:
            try:
                text = str(csv_file)
            except Exception:
                messages.error(request, "Unable to read uploaded file. Ensure it's a UTF-8 CSV.")
                return redirect(reverse("rawmaterials:inventory"))
    except Exception:
        messages.error(request, "Unable to read uploaded file. Ensure it's a UTF-8 CSV.")
        return redirect(reverse("rawmaterials:inventory"))

    if not text or not text.strip():
        messages.error(request, "Uploaded CSV appears empty.")
        return redirect(reverse("rawmaterials:inventory"))

    # --- detect delimiter using Sniffer (best-effort), fallback to comma ---
    sample_bytes = text[:4096]
    delimiter = ","
    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample_bytes, delimiters=[",", ";", "\t", "|"])
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ","

    # Build a DictReader
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        messages.error(request, "CSV appears malformed (no headers detected).")
        return redirect(reverse("rawmaterials:inventory"))

    # --- normalize header names: lower + replace non-word with underscore ---
    def _normalize_header_key(s: str) -> str:
        return re.sub(r"\W+", "_", s.strip().lower()) if s is not None else ""

    original_headers = [h for h in reader.fieldnames if h is not None]
    headers_norm_map = {}
    for h in original_headers:
        if not h:
            continue
        nk = _normalize_header_key(h)
        headers_norm_map[nk] = h  # normalized -> original

    # Small synonyms map (normalized form keys) to try when logical name isn't present
    SYNONYMS = {
        "cost_per_unit": ["cost_unit", "cost", "cost__unit", "cost_per_unit", "cost_unit_"],
        "item_name": ["item", "item_name", "name", "product", "item_name_"],
        "name": ["name", "item_name", "product"],
        "vendor": ["vendor", "vendor_name", "supplier", "supplier_name"],
        "stock": ["stock", "quantity", "qty", "stock_in_mtrs"],
        "width": ["width", "fabric_width"],
        "fabric_id": ["fabric_id", "fabric"],
        "fabric_item_name": ["fabric_item_name", "fabric_item", "fabric_name"],
        "product_type": ["product_type", "type"],
        "use_in": ["use_in", "usein", "use_in_"],
        # added synonyms for rate so CSVs using 'rate', 'price', 'unit_price' are accepted
        "rate": ["rate", "price", "unit_price", "unitprice"],
    }

    # helper: find normalized header in uploaded file and return the original header name if present
    def find_original_header(target_field_name: str):
        nk = _normalize_header_key(target_field_name)
        if nk in headers_norm_map:
            return headers_norm_map[nk]
        # try synonyms
        alt_list = SYNONYMS.get(target_field_name, [])
        for alt in alt_list:
            alt_nk = _normalize_header_key(alt)
            if alt_nk in headers_norm_map:
                return headers_norm_map[alt_nk]
        return None

    # Map logical fields -> actual header names (original)
    header_for = {}
    logical_fields = [
        "item_name", "name", "fabric_width", "quality", "stock", "cost_per_unit",
        "base_color", "type", "use_in", "vendor", "fabric_id", "fabric_item_name", "product_type", "width",
        "quantity_used", "unit", "rate"
    ]
    for lf in logical_fields:
        header_for[lf] = find_original_header(lf)

    # printed product logical uses 'name' header
    header_for["product"] = header_for.get("name") or header_for.get("item_name")

    # Helper: clean cell value -> None or cleaned string
    def clean_cell(v):
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        # Remove common trailing commas/spurious punctuation and NBSPs
        s = s.strip().rstrip(",").strip()
        s = s.replace("\u00A0", " ").strip()  # NBSP

        # If the cell is exactly a single common placeholder (hyphen/emdash/ndash) treat as missing.
        if len(s) == 1 and s in ("-", "—", "–"):
            return None

        # normalize common "missing" tokens (multi-char tokens)
        low = s.lower()
        if low in ("", "na", "n/a", "none", "null"):
            return None

        # otherwise preserve the value (including emdash/ndash if part of a longer string)
        return s

    # Helper to fetch logical field value (cleaned)
    def val_for(logical_field):
        hdr = header_for.get(logical_field)
        if not hdr:
            return None
        raw = raw_row.get(hdr)
        return clean_cell(raw)

    # Required per target (logical)
    if target == "fabric":
        required = ["item_name", "fabric_width"]
    elif target == "accessory":
        required = ["name"]  # accessory uses 'name' column per your spec
    elif target == "printed":
        required = ["name"]
    else:
        messages.error(request, "Unknown import target.")
        return redirect(reverse("rawmaterials:inventory"))

    # check required headers present
    missing = [r for r in required if not header_for.get(r)]
    if missing:
        messages.error(request, f"CSV missing required headers for {target}. Required (at least): {', '.join(missing)}")
        return redirect(reverse("rawmaterials:inventory"))

    created = []
    skipped = []
    errors = []
    new_vendors_created = []
    to_create_objs = []
    BATCH = 400

    # Helper to attempt resolving a Unit model and a unit instance by name
    UnitModel = None
    try:
        UnitModel = apps.get_model("rawmaterials", "Unit")
    except Exception:
        try:
            UnitModel = apps.get_model("units", "Unit")
        except Exception:
            UnitModel = None

    try:
        with transaction.atomic():
            for row_num, raw_row in enumerate(reader, start=2):
                # raw_row keys are original header names (as in the file)
                try:
                    if target == "fabric":
                        name = val_for("item_name") or val_for("name")
                        if not name:
                            raise ValueError("Missing 'item_name' / 'name' for fabric.")

                        fw = _parse_decimal(val_for("fabric_width"), required=True)
                        stock = _parse_decimal(val_for("stock"), default=None)
                        cost = _parse_decimal(val_for("cost_per_unit"), default=None)
                        quality = val_for("quality") or None
                        base_color = val_for("base_color") or None
                        ftype = val_for("type") or None
                        use_in = val_for("use_in") or None
                        vendor_val = val_for("vendor")
                        vendor_obj = _get_or_create_vendor(vendor_val) if vendor_val else None
                        if vendor_obj and vendor_obj.vendor_name not in new_vendors_created:
                            new_vendors_created.append(vendor_obj.vendor_name)

                        existing = Fabric.objects.filter(item_name__iexact=name.strip()).first()
                        if existing:
                            existing.fabric_width = fw if fw is not None else existing.fabric_width
                            if stock is not None:
                                existing.stock_in_mtrs = stock
                            if cost is not None:
                                existing.cost_per_unit = cost
                            existing.quality = (str(quality).strip() if quality not in (None, "") else existing.quality)
                            existing.base_color = base_color or existing.base_color
                            existing.type = ftype or existing.type
                            existing.use_in = use_in or existing.use_in
                            if vendor_obj:
                                existing.vendor = vendor_obj
                            existing.save()
                            created.append(f"(updated) {existing.item_name}")
                        else:
                            inst = Fabric(
                                item_name=name.strip(),
                                fabric_width=fw,
                                stock_in_mtrs=stock if stock is not None else Decimal("0.000"),
                                cost_per_unit=cost if cost is not None else Decimal("0.00"),
                                quality=(str(quality).strip() if quality not in (None, "") else None),
                                base_color=base_color or "",
                                type=ftype or "",
                                use_in=use_in or "",
                            )
                            if vendor_obj:
                                setattr(inst, "vendor_id", vendor_obj.pk)
                            to_create_objs.append(inst)
                            if len(to_create_objs) >= BATCH:
                                Fabric.objects.bulk_create(to_create_objs, batch_size=BATCH)
                                created.extend([getattr(x, "item_name", "") for x in to_create_objs])
                                to_create_objs = []

                    elif target == "accessory":
                        name = val_for("name") or val_for("item_name")
                        if not name:
                            raise ValueError("Missing 'name' for accessory (CSV header should include 'name').")

                        # clean numeric-ish inputs first (clean_cell removed commas/trailing commas)
                        width_raw = val_for("width")
                        width = _parse_decimal(width_raw, default=None) if width_raw is not None else None

                        stock_raw = val_for("stock")
                        stock = _parse_decimal(stock_raw, default=None) if stock_raw is not None else None

                        cost_raw = val_for("cost_per_unit")
                        cost = _parse_decimal(cost_raw, default=None) if cost_raw is not None else None

                        quality = val_for("quality") or None
                        base_color = val_for("base_color") or None
                        item_type = val_for("type") or None
                        use_in = val_for("use_in") or None

                        vendor_val = val_for("vendor")
                        vendor_obj = _get_or_create_vendor(vendor_val) if vendor_val else None
                        if vendor_obj and vendor_obj.vendor_name not in new_vendors_created:
                            new_vendors_created.append(vendor_obj.vendor_name)

                        existing = Accessory.objects.filter(item_name__iexact=name.strip()).first()
                        if existing:
                            if width is not None:
                                existing.width = width
                            if stock is not None:
                                existing.stock = stock
                            if cost is not None:
                                existing.cost_per_unit = cost
                            existing.quality = (str(quality).strip() if quality not in (None, "") else existing.quality)
                            existing.base_color = base_color or existing.base_color
                            existing.item_type = item_type or existing.item_type
                            existing.use_in = use_in or existing.use_in
                            if vendor_obj:
                                existing.vendor = vendor_obj
                            existing.save()
                            created.append(f"(updated) {existing.item_name}")
                        else:
                            inst = Accessory(
                                item_name=name.strip(),
                                width=width,
                                stock=stock if stock is not None else Decimal("0.000"),
                                cost_per_unit=cost if cost is not None else Decimal("0.00"),
                                quality=(str(quality).strip() if quality not in (None, "") else None),
                                base_color=base_color or "",
                                item_type=item_type or "",
                                use_in=use_in or "",
                            )
                            if vendor_obj:
                                setattr(inst, "vendor_id", vendor_obj.pk)
                            to_create_objs.append(inst)
                            if len(to_create_objs) >= BATCH:
                                Accessory.objects.bulk_create(to_create_objs, batch_size=BATCH)
                                created.extend([getattr(x, "item_name", "") for x in to_create_objs])
                                to_create_objs = []

                    elif target == "printed":
                        product_name = val_for("name")
                        if not product_name:
                            raise ValueError("Missing 'name' for printed product.")

                        fabric_obj = None
                        fid_val = val_for("fabric_id") or val_for("fabric")
                        if fid_val:
                            try:
                                fid = int(fid_val)
                                fabric_obj = Fabric.objects.filter(pk=fid).first()
                            except Exception:
                                fabric_obj = None
                        if not fabric_obj:
                            fab_name = val_for("fabric_item_name")
                            if fab_name:
                                fabric_obj = Fabric.objects.filter(item_name__iexact=fab_name).first()

                        base_color = val_for("base_color") or None
                        product_type = val_for("product_type") or val_for("type") or None
                        width = _parse_decimal(val_for("width"), default=None) if val_for("width") is not None else None
                        cost = _parse_decimal(val_for("cost_per_unit"), default=None) if val_for("cost_per_unit") is not None else None
                        quantity_used = _parse_decimal(val_for("quantity_used"), default=None) if val_for("quantity_used") is not None else None
                        if quantity_used is None or (isinstance(quantity_used, Decimal) and quantity_used <= Decimal("0")):
                            quantity_used_default_for_create = Decimal("0.001")
                        else:
                            quantity_used_default_for_create = quantity_used
                        stock = _parse_decimal(val_for("stock"), default=None) if val_for("stock") is not None else None
                        rate = _parse_decimal(val_for("rate"), default=None) if val_for("rate") is not None else None
                        quality = val_for("quality") or None
                        unit_val = val_for("unit") or None
                        vendor_val = val_for("vendor")
                        vendor_obj = _get_or_create_vendor(vendor_val) if vendor_val else None
                        if vendor_obj and vendor_obj.vendor_name not in new_vendors_created:
                            new_vendors_created.append(vendor_obj.vendor_name)

                        dup_qs = Printed.objects.filter(product__iexact=product_name.strip())
                        if fabric_obj:
                            dup_qs = dup_qs.filter(fabric=fabric_obj)
                        existing = dup_qs.first()

                        def _normalize_unit(u):
                            if not u:
                                return None
                            um = str(u).strip().lower()
                            if um in ("m", "meter", "meters", "metre", "metres"):
                                return "m"
                            if um in ("cm", "centimeter", "centimetre", "centimeters", "centimetres"):
                                return "cm"
                            if um in ("ft", "feet", "foot"):
                                return "ft"
                            return None

                        if existing:
                            if fabric_obj:
                                existing.fabric = fabric_obj
                            if base_color is not None:
                                existing.base_color = base_color
                            if product_type is not None:
                                existing.product_type = product_type
                            if width is not None:
                                existing.width = width
                            if cost is not None:
                                existing.cost_per_unit = cost
                            if quantity_used is not None:
                                existing.quantity_used = quantity_used
                            if stock is not None:
                                existing.stock = stock
                            if rate is not None:
                                existing.rate = rate
                            if quality not in (None, ""):
                                existing.quality = str(quality).strip()
                            if vendor_obj:
                                existing.vendor = vendor_obj
                            if unit_val:
                                ucode = _normalize_unit(unit_val)
                                if ucode:
                                    existing.unit = ucode
                                else:
                                    if UnitModel is not None:
                                        try:
                                            uobj = UnitModel.objects.filter(name__iexact=unit_val.strip()).first()
                                            if uobj:
                                                cand = getattr(uobj, "code", None) or getattr(uobj, "symbol", None) or getattr(uobj, "name", None)
                                                if cand:
                                                    uc = str(cand).strip().lower()
                                                    if uc in ("m", "cm", "ft"):
                                                        existing.unit = uc
                                        except Exception:
                                            pass
                            try:
                                existing.full_clean()
                                existing.save()
                                created.append(f"(updated) {existing.product}")
                            except Exception as e:
                                errors.append((row_num, f"Validation error updating printed '{product_name}': {e}"))
                        else:
                            printed_inst = Printed(
                                product=product_name.strip(),
                                fabric=fabric_obj,
                                base_color=base_color or "",
                                product_type=product_type or "",
                                width=width,
                                use_in=(val_for("use_in") or ""),
                                quality=(str(quality).strip() if quality not in (None, "") else None),
                                quantity_used=quantity_used_default_for_create,
                                stock=stock if stock is not None else Decimal("0.000"),
                                cost_per_unit=cost if cost is not None else Decimal("0.00"),
                                rate=rate if rate is not None else Decimal("0.00"),
                            )

                            ucode = _normalize_unit(unit_val)
                            if ucode:
                                printed_inst.unit = ucode
                            else:
                                if unit_val:
                                    try:
                                        uid_try = int(str(unit_val).strip())
                                        if UnitModel is not None:
                                            uobj = UnitModel.objects.filter(pk=uid_try).first()
                                            if uobj:
                                                cand = getattr(uobj, "code", None) or getattr(uobj, "symbol", None) or getattr(uobj, "name", None)
                                                if cand:
                                                    cand = str(cand).strip().lower()
                                                    if cand in ("m", "cm", "ft"):
                                                        printed_inst.unit = cand
                                    except Exception:
                                        if UnitModel is not None:
                                            try:
                                                uobj = UnitModel.objects.filter(name__iexact=unit_val.strip()).first()
                                                if uobj:
                                                    cand = getattr(uobj, "code", None) or getattr(uobj, "symbol", None) or getattr(uobj, "name", None)
                                                    if cand:
                                                        cand = str(cand).strip().lower()
                                                        if cand in ("m", "cm", "ft"):
                                                            printed_inst.unit = cand
                                            except Exception:
                                                pass

                            if vendor_obj:
                                setattr(printed_inst, "vendor_id", vendor_obj.pk)

                            try:
                                printed_inst.full_clean()
                                printed_inst.save()
                                created.append(getattr(printed_inst, "product", "") or str(printed_inst))
                            except Exception as e:
                                errors.append((row_num, f"Validation error creating printed '{product_name}': {e}"))

                    else:
                        raise ValueError("Unsupported target")

                except Exception as row_exc:
                    # include row number for debugging
                    errors.append((row_num, str(row_exc)))
                    # continue processing remaining rows

            # flush remaining bulk_create lists
            if to_create_objs:
                if target == "fabric":
                    Fabric.objects.bulk_create(to_create_objs, batch_size=BATCH)
                    created.extend([getattr(x, "item_name", "") for x in to_create_objs])
                elif target == "accessory":
                    Accessory.objects.bulk_create(to_create_objs, batch_size=BATCH)
                    created.extend([getattr(x, "item_name", "") for x in to_create_objs])

    except Exception as exc:
        messages.error(request, f"Import failed while processing file: {exc}")
        return redirect(reverse("rawmaterials:inventory"))

    # Build summary
    summary_parts = []
    if created:
        summary_parts.append(f"Created/Updated {len(created)} rows.")
    if skipped:
        summary_parts.append(f"Skipped {len(skipped)} rows (duplicates).")
    if errors:
        summary_parts.append(f"Errors in {len(errors)} rows; first errors: " +
                             "; ".join([f"row {r}: {msg}" for r, msg in errors[:4]]))
    if new_vendors_created:
        sample = ", ".join(new_vendors_created[:8])
        more = f", +{len(new_vendors_created)-8} more" if len(new_vendors_created) > 8 else ""
        summary_parts.append(f"Vendors created: {sample}{more}")

    if summary_parts:
        messages.success(request, " | ".join(summary_parts))
    else:
        messages.info(request, "No rows processed from CSV.")

    return redirect(reverse("rawmaterials:inventory"))


# ------------------------------
# Create / Edit views
# ------------------------------
@login_required
@user_passes_test(can_manage_inventory)
def accessory_create(request):
    if request.method == "POST":
        form = AccessoryForm(request.POST, request.FILES or None)
        if form.is_valid():
            form.save()
            messages.success(request, "Accessory created successfully.")
            return redirect(reverse("rawmaterials:inventory"))
    else:
        form = AccessoryForm()
    return render(request, "rawmaterials/accessory_form.html", {"form": form, "accessory": None})


@login_required
@user_passes_test(can_manage_inventory)
def accessory_edit(request, pk):
    accessory = get_object_or_404(Accessory, pk=pk)
    if request.method == "POST":
        form = AccessoryForm(request.POST, request.FILES or None, instance=accessory)
        if form.is_valid():
            form.save()
            messages.success(request, "Accessory updated successfully.")
            return redirect(reverse("rawmaterials:inventory"))
    else:
        form = AccessoryForm(instance=accessory)
    return render(request, "rawmaterials/accessory_form.html", {"form": form, "accessory": accessory})


@login_required
@user_passes_test(can_manage_inventory)
def fabric_create(request):
    if request.method == "POST":
        form = FabricForm(request.POST, request.FILES or None)
        if form.is_valid():
            form.save()
            messages.success(request, "Fabric created successfully.")
            return redirect(reverse("rawmaterials:inventory"))
    else:
        form = FabricForm()
    return render(request, "rawmaterials/fabric_form.html", {"form": form, "fabric": None, "can_delete": False})


@login_required
@user_passes_test(can_manage_inventory)
def fabric_edit(request, pk):
    fabric = get_object_or_404(Fabric, pk=pk)
    if request.method == "POST":
        form = FabricForm(request.POST, request.FILES or None, instance=fabric)
        if form.is_valid():
            form.save()
            messages.success(request, "Fabric updated successfully.")
            return redirect(reverse("rawmaterials:inventory"))
    else:
        form = FabricForm(instance=fabric)

    can_delete_flag = can_delete_inventory(request.user)
    return render(
        request,
        "rawmaterials/fabric_form.html",
        {"form": form, "fabric": fabric, "can_delete": can_delete_flag},
    )


@login_required
@user_passes_test(can_manage_inventory)
def printed_create(request):
    """
    Create Printed. If a 'fabric' GET param (fabric id) is provided, prefill the form's
    fabric-linked metadata from that Fabric (base_color, type, width, use_in, cost, vendor).
    """
    if request.method == "POST":
        form = PrintedForm(request.POST, request.FILES or None)
        if form.is_valid():
            form.save()
            messages.success(request, "Printed item created successfully.")
            return redirect(reverse("rawmaterials:inventory"))
    else:
        initial = {}
        fabric_id = request.GET.get("fabric") or request.GET.get("fabric_id")
        if fabric_id:
            try:
                fabric = Fabric.objects.select_related("vendor").get(pk=fabric_id)
                initial.update({
                    "fabric": fabric.pk,
                    "base_color": fabric.base_color,
                    "product_type": fabric.type,  # updated here
                    "width": fabric.fabric_width,
                    "use_in": fabric.use_in,
                    "cost_per_unit": fabric.cost_per_unit,
                    "vendor": fabric.vendor_id,
                })
            except Fabric.DoesNotExist:
                pass

        form = PrintedForm(initial=initial)

    return render(request, "rawmaterials/printed_form.html", {"form": form, "printed": None})


@login_required
@user_passes_test(can_manage_inventory)
def printed_edit(request, pk):
    printed = get_object_or_404(Printed, pk=pk)
    if request.method == "POST":
        form = PrintedForm(request.POST, request.FILES or None, instance=printed)
        if form.is_valid():
            form.save()
            messages.success(request, "Printed item updated successfully.")
            return redirect(reverse("rawmaterials:inventory"))
    else:
        form = PrintedForm(instance=printed)
    return render(request, "rawmaterials/printed_form.html", {"form": form, "printed": printed})


# ------------------------------
# Delete view for inventory items
# ------------------------------
@login_required
@user_passes_test(can_delete_inventory)
@require_POST
def inventory_delete(request, pk):
    instance = None
    model_label = None

    for model, label in ((Accessory, "Accessory"), (Fabric, "Fabric"), (Printed, "Printed")):
        try:
            instance = model.objects.get(pk=pk)
            model_label = label
            break
        except model.DoesNotExist:
            continue

    if not instance:
        messages.error(request, "Item not found or already deleted.")
        return redirect(reverse("rawmaterials:inventory"))

    display_name = None
    if model_label == "Fabric":
        display_name = getattr(instance, "item_name", None)
    display_name = display_name or getattr(instance, "name", None) or getattr(instance, "product", None) or str(instance)

    try:
        with transaction.atomic():
            if model_label == "Fabric":
                related_printeds_qs = getattr(instance, "printeds", None)
                related_printeds = list(related_printeds_qs.all()) if related_printeds_qs else list(Printed.objects.filter(fabric=instance))
                if related_printeds:
                    deleted_names = [str(p) for p in related_printeds]
                    if related_printeds_qs:
                        related_printeds_qs.all().delete()
                    else:
                        Printed.objects.filter(fabric=instance).delete()
                    messages.info(request, f"Deleted related Printed items: {', '.join(deleted_names)}")

            instance.delete()
        messages.success(request, f"{model_label} '{display_name}' deleted successfully.")

    except ProtectedError as e:
        protected_objs = getattr(e, "protected_objects", None) or []
        blocked_list = []
        try:
            for obj in protected_objs:
                blocked_list.append(f"{obj._meta.verbose_name.title()}: {str(obj)}")
        except Exception:
            blocked_list = [str(x) for x in protected_objs]

        if blocked_list:
            msg = f"Cannot delete {model_label} '{display_name}' because related records reference it: " + "; ".join(blocked_list)
        else:
            msg = f"Cannot delete {model_label} '{display_name}' because other records reference it."
        messages.error(request, msg)

    except Exception as exc:
        messages.error(request, f"An error occurred while deleting {model_label} '{display_name}': {exc}")

    return redirect(reverse("rawmaterials:inventory"))
