import os
import json
import time
import datetime
import requests
from dotenv import load_dotenv

utils_dir = os.path.dirname(os.path.abspath(__file__))
prompt_dir = os.path.abspath(os.path.join(utils_dir, ".."))

class GPTUtils:
    def __init__(self) -> None:
        config_dir = os.path.join(prompt_dir, "config")
        load_dotenv(os.path.join(config_dir, ".env"))

        self.api_key=os.environ["OPENAI_API_KEY"]
        pass

    def queryOpenAI(self, prompt, model, temperature, n) -> list:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"You are ChatGPT, a large language model trained by OpenAI, based on the GPT-4 architecture.\nKnowledge cutoff: 2023-04\nCurrent date: {datetime.date.today()}"},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "n": n
        }

        response = None
        while True:
            try:
                response = requests.post("https://api.openai.com/v1/chat/completions", data=json.dumps(data), headers=headers)
                response.raise_for_status()
                break
            except requests.RequestException as e:
                print(f"[x] Failed to call openai api: {e}. Retrying...")
                if response:
                    print(response.text)
                time.sleep(20)

        ret_json = response.json()
        
        if "error" in ret_json:
            print(f"[x] Failed to call openai api: {ret_json['error']['message']}")
            exit(1)
        
        ret_messages = []

        for choice in ret_json["choices"]:
            message = choice["message"]["content"]
            if choice['finish_reason'] == 'length':
                print("[INFO] The maximum number of tokens specified in the request was reached.")
            ret_messages.append(message)

        return ret_messages