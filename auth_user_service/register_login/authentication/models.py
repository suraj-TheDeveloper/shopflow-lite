from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import User

# Create your models here.
class UserModel(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(max_length=200, unique=True)
    password = models.CharField(max_length=250)
    role = models.CharField(max_length=50)

    class Meta:
        db_table = "users"

    def hash_password(self, raw_password):
        self.password = make_password(raw_password)

    def verify_password(self, user_password, hashed_password):
        return check_password(user_password, hashed_password)

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=50, default="user")

    class Meta:
        db_table = "profiles"