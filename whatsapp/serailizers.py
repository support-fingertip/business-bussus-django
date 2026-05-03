# serializers.py
from rest_framework import serializers

class ChatListSerializer(serializers.Serializer):
    sender = serializers.CharField()
    last_message = serializers.CharField()  # This will represent the last message, sent or received
    timestamp = serializers.DateTimeField()

    class Meta:
        fields = ['sender', 'last_message', 'timestamp']

    def to_representation(self, instance):
        """
        Custom `to_representation` method to decide which message to show (sent or received).
        """
        # Decide which message to use for `last_message` and `timestamp`
        last_message = instance.get('last_message_sent', None) or instance.get('last_message_received', None)
        last_timestamp = instance.get('last_timestamp_sent', None) or instance.get('last_timestamp_received', None)

        return {
            'sender': instance.get('sender'),
            'last_message': last_message,
            'timestamp': last_timestamp
        }
