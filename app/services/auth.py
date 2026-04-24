"""
Authentication system for a single recruiter user.
1. Login endpoint verifies the recruiter password and issues a JWT access token.
2. Protected recruiter routes use the get_current_recruiter() dependency, which:
   - extracts the token from the Authorization header,
   - validates the JWT,
   - checks that the subject matches the configured recruiter username.

JWT tokens are signed using the app’s SECRET_KEY and include an expiry time.
An additional "interview token" is supported, which encodes an interview_id
and is used for candidate interview links (valid for 24 hours).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from jose import JWTError, jwt # JWT is used for creating and verifying tokens
from passlib.context import CryptContext # CryptContext is used for hashing and verifying passwords
from fastapi import HTTPException, status, Depends # HTTPException is used for raising HTTP errors, status is used for HTTP status codes, Depends is used for dependency injection
from fastapi.security import OAuth2PasswordBearer # used for extracting tokens from requests

from app.utils.settings import settings

logger = logging.getLogger(__name__)

# bycrypt - used for password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto") # pw hashing

# OAuth2 scheme for token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")  #interaction with fastapi

class AuthManager:
    """
    Handles Recruiter Authentication (Single User).
    Uses JWT for session management and BCrypt for password hashing.
    """

    def __init__(self):  #it loads config values
        self._secret_key = settings.SECRET_KEY
        self._algorithm = settings.JWT_ALGORITHM
        self._expiry_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self._username = settings.RECRUITER_USERNAME
        self._password = settings.RECRUITER_PASSWORD

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Check if the provided password matches the configured one."""
        # If the .env password is the same as the plain one, accept it
        # This allows users to just type a password in .env without hashing it.
        if plain_password == self._password:  #allows plain ps in .env 
            return True
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """Hash a password for storage/comparison."""
        return pwd_context.hash(password)  #hashes the pw

    def create_access_token(self, data: dict, expires_delta: timedelta | None = None) -> str:   #adds expiration, uses algo to encode the token
        """Generate a new JWT token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta #
        else:
            expire = datetime.utcnow() + timedelta(minutes=self._expiry_minutes)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self._secret_key, algorithm=self._algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> str:
        """Verify a JWT token and return the subject (username)."""
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
            username: str = payload.get("sub")
            if username is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication token: missing subject",
                )
            return username
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
            )

    def create_interview_token(self, interview_id: str) -> str:
        """Generate a secure JWT for a candidate interview link (24h expiry)."""
        return self.create_access_token(
            data={
                "sub":  interview_id,
                "type": "interview",
                "jti":  str(uuid.uuid4()),   # unique per issuance — prevents identical tokens
            },
            expires_delta=timedelta(days=7)
        )

    def verify_interview_token(self, token: str) -> str:
        """Decode and verify an interview token, returning the interview_id."""
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
            if payload.get("type") != "interview":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type",
                )
            interview_id: str = payload.get("sub")
            if not interview_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token missing interview identifier",
                )
            return interview_id
        except (JWTError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired interview invitation",
            )

    async def get_current_recruiter(self, token: str = Depends(oauth2_scheme)) -> str:
        """Dependency to protect recruiter-only routes."""
        username = self.verify_token(token)
        if username != self._username:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource",
            )
        return username

auth_manager = AuthManager()  #startup
