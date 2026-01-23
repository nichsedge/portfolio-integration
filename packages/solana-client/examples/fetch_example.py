#!/usr/bin/env python3
"""Example usage of the solana-client package."""

import os
from dotenv import load_dotenv
from solana_client import main

if __name__ == "__main__":
    # Load environment variables from .env file
    load_dotenv()
    
    # Check if wallet address is set
    if not os.getenv("SOLANA_WALLET_ADDRESS"):
        print("Please set SOLANA_WALLET_ADDRESS in your .env file")
        print("Example: SOLANA_WALLET_ADDRESS=CONFIDENTIAL_ADDRESS")
        exit(1)
    
    # Run the fetcher
    main()
