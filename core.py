from fastapi import Header,HTTPException,Depends

VALID_API_KEYS={
    "api-key-001":"tenant_1",
    "api-key-002":"tenant_2",
    "api-key-003":"tenant_3",
}

def get_current_tenant(x_api_key:str=Header(...)):
    tenant=VALID_API_KEYS.get(x_api_key)
    if not tenant:
        raise HTTPException(status_code=401,detail="Invalid API Key")
    return tenant