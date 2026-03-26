from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
import logging

from app.models import (
    create_access_token,
    query_transaction_status,
    SECRET_KEY,
    ALGORITHM
)

app = FastAPI(title="MPESA Transaction Status API")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="merchant-login")

logging.basicConfig(level=logging.INFO)

# =========================
# TEMP STORAGE (saves on memory)
# =========================
# Stores callback results by TransactionID
transaction_results = {}
transaction_acknowledgments = {}


# =========================
# LOGIN ENDPOINT
# =========================
@app.post("/merchant-login")
def login():
    """
    Generate token for merchant
    """
    token = create_access_token({"username": "demo_merchant"})
    return {"access_token": token, "token_type": "bearer"}


# =========================
# AUTH VALIDATION
# =========================
def get_current_merchant(token: str = Depends(oauth2_scheme)):
    """
    Validate JWT token
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("username")

        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")

        return {"username": username}

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# =========================
# TRANSACTION QUERY
# =========================
import asyncio

@app.get("/query/transaction-status/{transaction_id}")
async def query_status(transaction_id: str, current=Depends(get_current_merchant)):
    try:
        # 1. Trigger the query to Safaricom
        response = query_transaction_status(transaction_id)
        logging.info(f"MPESA ACK Received: {response}")

        # 2. Poll the local dictionary for the result (max 5 seconds)
        for _ in range(10):  # Check 10 times
            await asyncio.sleep(0.5)  # Wait 500ms between checks
            
            # Look for the result stored by your /result endpoint
            if transaction_id in transaction_results:
                final_data = transaction_results.pop(transaction_id) # Get and clear
                return {
                    "status": "Success",
                    "data": final_data
                }

        return {
            "status": "Pending",
            "message": "Safaricom is processing your request",
            "mpesa_ack": response
        }

    except Exception as e:
        logging.error(f"Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# =========================
# RESULT CALLBACK (IMPORTANT)
# =========================
@app.post("/result")
async def result_callback(req: Request):
    data = await req.json()
    logging.info(f" RESULT CALLBACK RECEIVED: {data}")

    try:
        result = data.get("Result", {})
        transaction_id = result.get("TransactionID")

        params_list = result.get("ResultParameters", {}).get("ResultParameter", [])

        payload_structure = {
            "TransactionID": transaction_id,
            "ResultCode": result.get("ResultCode"),
            "ResultDesc": result.get("ResultDesc"),
            "OriginatorConversationID": result.get("OriginatorConversationID"),
            "ConversationID": result.get("ConversationID"),
            "Occasion": result.get("ReferenceData", {}).get("ReferenceItem", {}).get("Value"),
            "Details": {param["Key"]: param.get("Value") for param in params_list}  # <-- safer
        }

        transaction_results[transaction_id] = payload_structure
        logging.info(f"Stored transaction result for {transaction_id}")

        return {"ResultCode": 0, "ResultDesc": "Accepted"}

    except Exception as e:
        logging.error(f"Error parsing callback: {e}")
        return {"ResultCode": 1, "ResultDesc": str(e)}


# =========================
# TIMEOUT CALLBACK
# =========================
@app.post("/timeout")
async def timeout_callback(req: Request):
    """
    MPESA sends timeout notification here
    """
    data = await req.json()

    logging.warning(f"⏱️ TIMEOUT CALLBACK: {data}")

    return {"ResultCode": 0, "ResultDesc": "Accepted"}


# =========================
# FETCH RESULT BY TRANSACTION ID
# =========================
@app.get("/result/{transaction_id}")
def get_result(transaction_id: str):
    """
    Step 3:
    Retrieve stored MPESA result using TransactionID.
    If callback hasn't arrived yet, return last ACK or pending status.
    """
    if transaction_id in transaction_results:
        return transaction_results[transaction_id]

    elif transaction_id in transaction_acknowledgments:
        return {
            "message": "Transaction ACK received, result pending",
            "mpesa_ack": transaction_acknowledgments[transaction_id]
        }

    else:
        return {"message": "No record of this TransactionID"}