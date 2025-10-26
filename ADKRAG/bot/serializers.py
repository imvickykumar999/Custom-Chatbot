from rest_framework import serializers
from .models import ScrapedDataEntry

class ScrapedDataEntrySerializer(serializers.ModelSerializer):
    """
    Serializer for the ScrapedDataEntry model.
    """
    class Meta:
        model = ScrapedDataEntry
        fields = '__all__'
