from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import CategoryMaster, CategoryMasterNew
from .forms import CategoryMasterForm


@admin.register(CategoryMasterNew)
class CategoryMasterNewAdmin(admin.ModelAdmin):
    """
    Admin for the CategoryMasterNew master-dropdown entries.
    """
    list_display = ("name", "active", "created_at")
    list_filter = ("active",)
    search_fields = ("name",)
    ordering = ("name",)
    actions = ("make_active", "make_inactive")

    @admin.action(description=_("Mark selected categories as active"))
    def make_active(self, request, queryset):
        updated = queryset.update(active=True)
        self.message_user(request, _("%d categories marked as active.") % updated)

    @admin.action(description=_("Mark selected categories as inactive"))
    def make_inactive(self, request, queryset):
        updated = queryset.update(active=False)
        self.message_user(request, _("%d categories marked as inactive.") % updated)


@admin.register(CategoryMaster)
class CategoryMasterAdmin(admin.ModelAdmin):
    """
    Admin for CategoryMaster entries. Uses the custom ModelForm for validation and widgets.
    """
    form = CategoryMasterForm

    list_display = (
        "component_name",
        "gf_overhead_display",
        "texas_buying_cost_display",
        "texas_retail_display",
        "shipping_cost_inr_display",
        "texas_to_us_selling_cost_display",
        "import_cost_display",
        "new_tariff_display",
        "reciprocal_tariff_display",
        "shipping_us_display",
        "us_wholesale_margin_display",
        "created_at",
    )

    list_select_related = ("component",)
    search_fields = ("component__name",)
    list_display_links = ("component_name",)
    list_filter = ("component__active", "created_at")
    list_per_page = 50
    actions = ("reset_percentages_to_zero",)

    # ----- Helper display methods (formats values for admin list) -----
    def _fmt_percent(self, value):
        """
        Format Decimal percentage values for display in admin list (e.g., 12.34 -> "12.34%").
        Handles None gracefully.
        """
        if value is None:
            return ""
        # Use str() to preserve Decimal formatting; append percent sign.
        return f"{value}%"

    def _fmt_currency(self, value):
        """
        Format numeric currency fields (INR) for admin display.
        """
        if value is None:
            return ""
        # show two decimal places consistently
        return f"{value:.2f}"

    @admin.display(description=_("Category (from master)"), ordering="component__name")
    def component_name(self, obj):
        comp = getattr(obj, "component", None)
        if not comp:
            return ""
        return getattr(comp, "name", str(comp))

    @admin.display(description=_("GF Overhead (%)"), ordering="gf_overhead")
    def gf_overhead_display(self, obj):
        return self._fmt_percent(obj.gf_overhead)

    @admin.display(description=_("Texas Buying Cost (%)"), ordering="texas_buying_cost")
    def texas_buying_cost_display(self, obj):
        return self._fmt_percent(obj.texas_buying_cost)

    @admin.display(description=_("Texas Retail (%)"), ordering="texas_retail")
    def texas_retail_display(self, obj):
        return self._fmt_percent(obj.texas_retail)

    @admin.display(description=_("Shipping Cost (INR)"), ordering="shipping_cost_inr")
    def shipping_cost_inr_display(self, obj):
        return self._fmt_currency(obj.shipping_cost_inr)

    @admin.display(description=_("Texas → US Selling Cost (%)"), ordering="texas_to_us_selling_cost")
    def texas_to_us_selling_cost_display(self, obj):
        return self._fmt_percent(obj.texas_to_us_selling_cost)

    @admin.display(description=_("Import (%)"), ordering="import_cost")
    def import_cost_display(self, obj):
        return self._fmt_percent(obj.import_cost)

    @admin.display(description=_("New Tariff (%)"), ordering="new_tariff")
    def new_tariff_display(self, obj):
        return self._fmt_percent(obj.new_tariff)

    @admin.display(description=_("Reciprocal Tariff (%)"), ordering="reciprocal_tariff")
    def reciprocal_tariff_display(self, obj):
        return self._fmt_percent(obj.reciprocal_tariff)

    @admin.display(description=_("Shipping US (%)"), ordering="shipping_us")
    def shipping_us_display(self, obj):
        return self._fmt_percent(obj.shipping_us)

    @admin.display(description=_("US Wholesale Margin (%)"), ordering="us_wholesale_margin")
    def us_wholesale_margin_display(self, obj):
        return self._fmt_percent(obj.us_wholesale_margin)

    # ----- Admin actions -----
    @admin.action(description=_("Reset selected percentage fields to 0"))
    def reset_percentages_to_zero(self, request, queryset):
        """
        Bulk action to reset all percentage fields to 0.00 on selected CategoryMaster records.
        Useful when doing wide re-pricing or clearing test data.
        """
        fields_to_reset = [
            "gf_overhead",
            "texas_buying_cost",
            "texas_retail",
            "texas_to_us_selling_cost",
            "import_cost",
            "new_tariff",
            "reciprocal_tariff",
            "shipping_us",
            "us_wholesale_margin",
        ]
        updated = queryset.update(**{f: 0 for f in fields_to_reset})
        self.message_user(request, _("%d CategoryMaster records updated (percentages set to 0).") % updated)
