"""
handles the login of the recruiter.
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.services.auth import auth_manager
from app.utils.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    username: str

@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):  #provides username and pw
    """
    Accepts username and password
    """
    #  Verify username
    if form_data.username != settings.RECRUITER_USERNAME: #username check
        logger.warning(f"Failed login attempt for username: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    #  Verify password
    # We check against the plain text setting from .env for maximum simplicity as requested
    if not auth_manager.verify_password(form_data.password, ""):  #pw from .env and not db
        logger.warning(f"Failed login attempt for user: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create token (jwt)
    access_token = auth_manager.create_access_token(
        data={"sub": form_data.username}   #a signed jwt token is created
    )
    
    logger.info(f"Recruiter logged in: {form_data.username}")   #returns a json response 
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "username": form_data.username
    }
