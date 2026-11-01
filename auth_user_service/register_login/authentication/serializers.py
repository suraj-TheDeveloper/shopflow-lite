from django.contrib.auth.models import User
from rest_framework import serializers
from .models import *

class RegisterRequest(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Email already registered")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["email"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data["name"],
        )
        Profile.objects.create(user=user, role="user")
        return user

class LoginRequest(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()