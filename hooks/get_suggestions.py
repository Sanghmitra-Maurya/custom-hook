import os
from openai import OpenAI
from hooks.setup_details import get_decrypted_tokens

# Load token from encrypted key
tokens = get_decrypted_tokens()
HF_TOKEN = tokens["HF_TOKEN"]
if not HF_TOKEN:
    raise ValueError("HF_TOKEN environment variable is not set.")


# Create HF Inference client with Novita provider (LLaMA 3.1)
client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=HF_TOKEN,
)

def get_code_suggestion_from_error(prompt: str) -> str:
    """
    Sends the full prompt (already formatted) to LLaMA 3.1 via Hugging Face.

    Args:
        prompt (str): A complete prompt including error message + code context.

    Returns:
        str: LLM-generated suggestion (code fix or resolution).
    """
    try:
        completion = client.chat.completions.create(
            model="meta-llama/Llama-3.1-8B-Instruct:novita",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
        )
        return completion.choices[0].message.content.strip()

    except Exception as e:
        return f"[Error contacting Hugging Face Novita API]: {repr(e)}"
