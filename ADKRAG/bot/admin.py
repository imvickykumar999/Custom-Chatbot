from django.contrib import admin
from .models import ScrapedDataEntry

# Customizing the display of the ScrapedDataEntry model in the Admin
class ScrapedDataEntryAdmin(admin.ModelAdmin):
    # Fields to display in the main list view
    list_display = ('url', 'scraped_by_user_id', 'scrape_mode', 'scraped_at', 'name_display')
    
    # Fields to link to the detail view (where you can edit)
    list_display_links = ('url', 'name_display')
    
    # Fields that can be used to filter the list view
    list_filter = ('scrape_mode', 'scraped_at')
    
    # Fields to use for search (searches across these fields)
    search_fields = ('url', 'name', 'meta_description', 'scraped_by_user_id')

    # Read-only fields in the detail view
    readonly_fields = ('scraped_at',)

    # Custom method to display a shorter or more friendly name in the list view
    def name_display(self, obj):
        # Shows the H1 tag content, or the first 50 characters of the URL if H1 is missing
        if obj.name:
            return obj.name
        return f"({obj.url[:50]}...)"
    name_display.short_description = 'Name / H1'
    
    # Fieldset configuration for the detail view (optional, but helps organization)
    fieldsets = (
        ('Scraping Metadata', {
            'fields': ('scraped_by_user_id', 'scrape_mode', 'scraped_at'),
        }),
        ('SEO & Content', {
            'fields': ('url', 'name', 'meta_title', 'meta_description', 'meta_keywords', 'content_summary'),
        }),
    )

# Register the model with the customized admin class
admin.site.register(ScrapedDataEntry, ScrapedDataEntryAdmin)
