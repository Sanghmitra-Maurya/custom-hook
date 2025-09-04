from cryptography.fernet import Fernet

FERNET_KEY=b"2FNrAq6zbj0jXILjO94Ty3yhs_haF6PFs0_uChMUVkQ="
ENCRYPTED_SONAR=b"gAAAAABouT8kyOmgZ1XGt4ttgFWjoWN5bbcQ14MZ9dphi4q3Js7rrIArOMhIb1LGXl77tpcHG1qX9m1miSIDijX4OqY8GZPeyfgQNiIcpbP-Q5wnvK3O9F-ljychZbaD-2cDjpIHKMWw"
ENCRYPTED_HF=b"gAAAAABouT8kLUb6Va6MM3JSah8mHTD-b-SsX5pNFtS3a87_Pgulv4JBLn78QdolD6cD0-16ekdaUzN3zRzEDwBZDKnkywepHBrHPa17Ci4tMu1JbLMzsIHEZKHHT6G8tMn0nHfb1b1P"

def get_decrypted_tokens():
    f = Fernet(FERNET_KEY)
    sonar_token = f.decrypt(ENCRYPTED_SONAR).decode()
    hf_token = f.decrypt(ENCRYPTED_HF).decode()
    
    return {
        "SONAR_TOKEN": sonar_token,
        "HF_TOKEN": hf_token
    }