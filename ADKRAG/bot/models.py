from django.db import models

class ScrapedDataEntry(models.Model):
    # The normalized URL (e.g., without trailing slash). Must be unique.
    url = models.URLField(max_length=2000, unique=True, verbose_name="Source URL")
    
    # Metadata fields
    name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Name / H1")
    meta_title = models.CharField(max_length=255, null=True, blank=True)
    meta_description = models.TextField(null=True, blank=True)
    meta_keywords = models.CharField(max_length=500, null=True, blank=True)
    
    # Scraper information
    scraped_by_user_id = models.CharField(max_length=50, verbose_name="Scraped by user id")
    scrape_mode = models.CharField(max_length=10, choices=[
        ('single', 'Single Page'), 
        ('sitemap', 'Full Sitemap')
    ], default='single')
    scraped_at = models.DateTimeField(auto_now_add=True)
    
    # Content summary (since the full content is too big/complex for a simple model field)
    content_summary = models.TextField(verbose_name="Content Summary (First 500 chars)", null=True, blank=True)

    class Meta:
        verbose_name = "Scraped Data Entry"
        verbose_name_plural = "Scraped Data Entries"
        ordering = ['-scraped_at']

    def __str__(self):
        return f"{self.url} ({self.scrape_mode})"
