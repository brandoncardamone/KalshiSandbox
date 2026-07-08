from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.exceptions import InvalidSignature

import requests
import datetime

import os
from dotenv import load_dotenv

#import pprint #experimental formatting import
import json #attempt 2

load_dotenv()

api_key_id = os.getenv("KALSHI_API_KEY_ID")
api_key_path = os.getenv("KALSHI_API_KEY_PATH")

def load_private_key_from_file(file_path):
    with open(file_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=None,  # or provide a password if your key is encrypted
            backend=default_backend()
        )
    return private_key

def sign_pss_text(private_key: rsa.RSAPrivateKey, text: str) -> str:
    message = text.encode('utf-8')
    try:
        signature = private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode('utf-8')
    except InvalidSignature as e:
        raise ValueError("RSA sign PSS failed") from e

#print(load_private_key_from_file(r"C:\Users\bcard\OneDrive\Desktop\Projects\KalshiSandbox\first key.txt"))
#print(load_private_key_from_file(api_key_path))

current_time = datetime.datetime.now()
timestamp = current_time.timestamp()
current_time_milliseconds = int(timestamp * 1000)
timestampt_str = str(current_time_milliseconds)

private_key = load_private_key_from_file(api_key_path)

method = "GET"
base_url = 'https://external-api.kalshi.com'
path='/trade-api/v2/portfolio/positions'

# Strip query parameters from path before signing
path_without_query = path.split('?')[0]
msg_string = timestampt_str + method + path_without_query
sig = sign_pss_text(private_key, msg_string)

headers = {
    'KALSHI-ACCESS-KEY': api_key_id,
    'KALSHI-ACCESS-SIGNATURE': sig,
    'KALSHI-ACCESS-TIMESTAMP': timestampt_str
}

response1 = requests.get(base_url + path, headers=headers)



response2 = requests.get(base_url + path, headers=headers)

#print(response1.text)
#print()

#pprint.pp(response.text, sort_dicts=True)
print(json.dumps(response1.json(), indent=2))

#print(msg_string)
#print(sig)
#print()
#print(response1.json()["market_positions"])

#print()
#print("Just the france")
#print(json.dumps(response1.json()["market_positions"][0]["ticker"], indent=2))

list_of_positions = response1.json()["market_positions"]



list_of_cur_perc = [] #list of the current percentages
for i in range(len(list_of_positions)):
    list_of_cur_perc.append("pass")

print(list_of_cur_perc)