import os
import requests
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from jose import jwt


# imports from crytography that are used for handling certificate and key encryption 
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
import base64

load_dotenv()

# =========================
# ENV CONFIGURATION
# =========================
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

MPESA_BASE_URL = os.getenv("MPESA_BASE_URL")
CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")
SHORTCODE = os.getenv("MPESA_SHORTCODE")
INITIATOR = os.getenv("MPESA_INITIATOR")
RESULT_URL = os.getenv("MPESA_RESULT_URL")
TIMEOUT_URL = os.getenv("MPESA_TIMEOUT_URL")




# =========================
# JWT TOKEN GENERATION
# =========================
def create_access_token(data: dict):
    """
    Create JWT token for merchant authentication
    """
    expire = datetime.utcnow() + timedelta(minutes=60)
    data.update({"exp": expire})
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


# =========================
# MPESA AUTH (OAuth Token)
# =========================
def get_mpesa_access_token():
    """
    Get OAuth access token from MPESA API
    """
    url = f"{MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"

    response = requests.get(url, auth=(CONSUMER_KEY, CONSUMER_SECRET))

    if response.status_code != 200:
        logging.error(f"MPESA Token Error: {response.text}")
        raise Exception("Failed to get MPESA access token")

    return response.json().get("access_token")


# =========================
# TRANSACTION STATUS QUERY
# =========================
def query_transaction_status(transaction_id: str):
    """
    Sends transaction status query to MPESA using TransactionID

    NOTE:
    - This bypases the iniator and username credential because its a query for C2B
    - Actual result comes via ResultURL callback
    """
    access_token = get_mpesa_access_token()

    url = f"{MPESA_BASE_URL}/mpesa/transactionstatus/v1/query"

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    payload = {
       "Initiator": INITIATOR,
       "SecurityCredential": SECURITY_CREDENTIAL,
        "CommandID": "TransactionStatusQuery",
        "TransactionID": transaction_id,  # Key field that identifes the exact trasaction  
        "PartyA": SHORTCODE,
        "IdentifierType": "4",
        "ResultURL": RESULT_URL,
        "QueueTimeOutURL": TIMEOUT_URL,
        "Remarks": "Transaction Query",
        "Occasion": "Status Check"
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code != 200:
        logging.error(f"MPESA API Error: {response.text}")
        raise Exception("MPESA request failed")

    return response.json()  


#===========================
#Certificate encryption
#==========================

#this function encrypts the password for secrete credential that enables end-to-end production from the callback response

def generate_security_credential(cert_path: str, initiator_password: str):
    
   # Encrypt Initiator password using Safaricom certificate (PEM format)

    with open(cert_path, "rb") as cert_file:
        cert_data = cert_file.read()

        # Load PEM certificate
        cert = x509.load_pem_x509_certificate(cert_data, default_backend())

        # Extract public key
        public_key = cert.public_key()

    encrypted = public_key.encrypt(
        initiator_password.encode(),
        padding.PKCS1v15()
    )

    return base64.b64encode(encrypted).decode()


#========================
# Generating the credential 
#=======================

initiator_password = os.getenv("MPESA_INITIATOR_PASSWORD")

if not initiator_password:
    raise ValueError("MPESA_INITIATOR_PASSWORD is not set")

SECURITY_CREDENTIAL = generate_security_credential(
        "certificate/production.cer", # path to where the .cer file is
        initiator_password
    )


#For Loggs to check if all functions arecorrectly working

if __name__ == "__main__":
    print("Running credential generator...  \n")

    print("SecurityCredential:\n", SECURITY_CREDENTIAL)

    print("INITIATOR:", INITIATOR)

