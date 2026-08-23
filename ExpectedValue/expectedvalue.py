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

def my_get_function(path) -> requests.models.Response:
    current_time = datetime.datetime.now()
    timestamp = current_time.timestamp()
    current_time_milliseconds = int(timestamp * 1000)
    timestampt_str = str(current_time_milliseconds)

    private_key = load_private_key_from_file(api_key_path)

    method = "GET"
    base_url = 'https://external-api.kalshi.com'
    #path='/trade-api/v2/portfolio/positions'

    # Strip query parameters from path before signing
    path_without_query = path.split('?')[0]
    msg_string = timestampt_str + method + path_without_query
    sig = sign_pss_text(private_key, msg_string)

    headers = {
        'KALSHI-ACCESS-KEY': api_key_id,
        'KALSHI-ACCESS-SIGNATURE': sig,
        'KALSHI-ACCESS-TIMESTAMP': timestampt_str
    }

    return requests.get(base_url + path, headers=headers)

def my_expected_value(response1) -> float:
    list_of_positions = response1.json()["market_positions"]

    list_of_position_fp = []
    list_of_last_price_dollars = []

    list_of_tickers = [] #List of the names of the item bought
    for i in range(len(list_of_positions)): #Populates list
        list_of_tickers.append(list_of_positions[i]["ticker"])

    #Populates list of position_fp for each ticker
    for i in range(len(list_of_positions)):
        list_of_position_fp.append(list_of_positions[i]["position_fp"])

    #Populates list of last_price_dollars
    for i in range(len(list_of_positions)):
        specific_ticker = my_get_function(f'/trade-api/v2/markets/{list_of_tickers[i]}').json()
        list_of_last_price_dollars.append(specific_ticker["market"]["last_price_dollars"])

    #Calculates the expected value
    expected_value = sum(float(a) * float(b) for a, b in zip(list_of_position_fp, list_of_last_price_dollars))
    
    return expected_value

def my_expected_profit(response1, expected_value) -> float:
    list_of_positions = response1.json()["market_positions"]
    
    list_of_costs = []
    for i in range(len(list_of_positions)):
        list_of_costs.append(float(list_of_positions[i]["fees_paid_dollars"])+float(list_of_positions[i]["market_exposure_dollars"]))

    return(expected_value - sum(a for a in list_of_costs))

#response1 = requests.get(base_url + path, headers=headers)
response1 = my_get_function('/trade-api/v2/portfolio/positions')

#response2 = requests.get(base_url + path, headers=headers)

#print(response1.text)
#print()

#pprint.pp(response.text, sort_dicts=True)

#USEFUL
#print(json.dumps(response1.json(), indent=2))
#USEFUL


#print(msg_string)
#print(sig)
#print()
#print(response1.json()["market_positions"])

#print()
#print("Just the france")
#print(json.dumps(response1.json()["market_positions"][0]["ticker"], indent=2))


#print(json.dumps(my_get_function(f'/trade-api/v2/markets/{list_of_tickers[0]}').json(), indent=2))

#print(list_of_tickers)
#print(list_of_position_fp)
#print(list_of_last_price_dollars)

expected_value = my_expected_value(response1)
print(f"Expected value of positions: {expected_value}")

print(f"Expected profit of positions: {my_expected_profit(response1, expected_value)}")