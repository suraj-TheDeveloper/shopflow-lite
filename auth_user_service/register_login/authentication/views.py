from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth import authenticate
from rest_framework.permissions import IsAuthenticated
from .serializers import RegisterRequest, LoginRequest
from rest_framework.views import APIView
from .models import *

# Create your views here.
@api_view(['POST'])
def register(request):
    userData = RegisterRequest(data=request.data)
    if userData.is_valid():
        userData.save()
        return Response("User Registered Successfully", 201)
    else:
        return Response("Data missing", 400)

@api_view(['POST'])
def login(request):
    serializer = LoginRequest(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = authenticate(
        username=serializer.validated_data["email"],
        password=serializer.validated_data["password"],
    )
    if user is None:
        return Response({"detail": "Email or password is wrong"}, status=401)

    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.profile.role
    refresh["name"] = user.first_name
    refresh["email"] = user.email
    return Response({
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
    })
    
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def me(request):
    data = request.user
    payload = {
        "id": data.id,
        "name": data.first_name,
        "email": data.email,
        "role": data.profile.role
    }
    return Response(payload, 200)

class VerfiyTokenView(APIView):
    authentication_classes = [JWTAuthentication]
    permisson_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        print("user", user)
        return Response({
            "id": user.id,
            "email": user.email,
        })