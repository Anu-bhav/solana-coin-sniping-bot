# Solana.py and Solders API Reference Summary

This document summarizes key API details, type definitions, and error structures from `solana-py` and `solders`, focusing on aspects relevant to RPC interactions, transaction handling, and common error types based on the provided documentation URLs.

**Note:** Core types previously in `solana-py` have largely moved to the `solders` library. `solana-py` now uses `solders` extensively under the hood.

## Solana.py (`solana` package)

Provides the Python SDK for interacting with the Solana JSON RPC API and includes helpers for SPL interactions.

### RPC Client (`solana.rpc.api.Client`)

Used for making synchronous calls to the Solana RPC endpoint.

**Key Methods:**

*   `send_transaction(txn: Union[VersionedTransaction, Transaction], opts: Optional[TxOpts]) -> SendTransactionResp`: Sends a signed transaction. Performs preflight checks by default.
*   `confirm_transaction(tx_sig: Signature, commitment: Optional[Commitment], ...) -> GetSignatureStatusesResp`: Polls the network to confirm a transaction signature reaches a specified commitment level.
*   `simulate_transaction(txn: Union[Transaction, VersionedTransaction], ...) -> SimulateTransactionResp`: Simulates a transaction without sending it to the network. Useful for checking potential errors and estimating compute units.
*   `get_transaction(tx_sig: Signature, encoding: str, ...) -> GetTransactionResp`: Retrieves details for a confirmed transaction. Supports various encodings (`json`, `jsonParsed`, `base64`).
*   `get_account_info(pubkey: Pubkey, ...) -> GetAccountInfoResp`: Gets account details (lamports, owner, data).
*   `get_account_info_json_parsed(pubkey: Pubkey, ...) -> GetAccountInfoMaybeJsonParsedResp`: Gets account details, attempting to parse known program data (like SPL Token accounts) into JSON.
*   `get_balance(pubkey: Pubkey, ...) -> GetBalanceResp`: Gets the lamport balance of an account.
*   `get_latest_blockhash(...) -> GetLatestBlockhashResp`: Fetches the latest blockhash and the last valid block height for transaction construction.
*   `get_token_account_balance(pubkey: Pubkey, ...) -> GetTokenAccountBalanceResp`: Gets the token balance for an SPL Token account.
*   `get_token_accounts_by_owner(owner: Pubkey, opts: TokenAccountOpts, ...) -> GetTokenAccountsByOwnerResp`: Gets all SPL token accounts owned by a specific public key, optionally filtered by mint or program ID.
*   `get_token_supply(pubkey: Pubkey, ...) -> GetTokenSupplyResp`: Gets the total supply for an SPL Token mint.
*   `get_signature_statuses(signatures: List[Signature], ...) -> GetSignatureStatusesResp`: Checks the confirmation status of one or more transaction signatures.

**RPC Responses:**

Methods return response objects (e.g., `SendTransactionResp`, `GetTransactionResp`) typically containing a `value` attribute holding the actual data (like a `Signature`, `RpcTransaction`, `Account`, `UiTokenAmount`, etc.). These response types often wrap underlying `solders` types.

**Common Exceptions:**

*   `solana.rpc.core.RPCException`: General exception for RPC errors returned by the node. The error payload often contains more specific details.
*   `solana.rpc.core.UnconfirmedTxError`: Raised by `confirm_transaction` if the transaction doesn't reach the desired commitment level within the timeout.
*   `solana.rpc.core.TransactionExpiredBlockheightExceededError`: Raised by `confirm_transaction` if the transaction expires due to exceeding its `last_valid_block_height`.

### SPL Token Client (`spl.token.client.Token`)

Provides helpers for interacting with the SPL Token program. (Note: The fetched docs mainly covered the intro; detailed methods are in sub-pages not fetched in this task). It uses the `solana.rpc.api.Client` internally.

## Solders (`solders` package)

Provides core Solana data structures and types, implemented in Rust for performance. Used by `solana-py`.

### Core Types

*   `solders.pubkey.Pubkey`: Represents a Solana public key.
*   `solders.keypair.Keypair`: Represents a public/private key pair for signing.
*   `solders.signature.Signature`: Represents a transaction signature.
*   `solders.hash.Hash`: Represents a blockhash.
*   `solders.instruction.Instruction`: Represents a single instruction within a transaction.
    *   `solders.instruction.AccountMeta`: Defines an account required by an instruction (pubkey, is_signer, is_writable).
*   `solders.message.Message`: The core content of a transaction (instructions, accounts, recent blockhash).
    *   `solders.message.MessageV0`: Version 0 message format supporting Address Lookup Tables (ALT).
*   `solders.transaction.Transaction`: Legacy transaction format.
*   `solders.transaction.VersionedTransaction`: Wrapper for different transaction versions (Legacy or V0).

### RPC Related Types (`solders.rpc.*`)

Contains types used for building RPC requests and parsing responses (used by `solana-py`). Includes request/response structures, configuration objects (`CommitmentConfig`), filters (`RpcFilterType`), etc.

### Account Decoder Types (`solders.account_decoder.*`)

*   `solders.account_decoder.UiTokenAmount`: Represents token amount with decimals, used in parsed JSON responses (e.g., from `get_token_account_balance`).
    ```python
    UiTokenAmount(
        amount='1000', 
        decimals=9, 
        ui_amount=1e-06, 
        ui_amount_string='0.000001'
    )
    ```

### Transaction Status & Errors (`solders.transaction_status.*` and `solders.transaction.*`)

These modules define structures related to transaction outcomes and errors found within transaction metadata or simulation results.

*   **`solders.transaction_status.TransactionStatus`**: Represents the status of a transaction queried via `get_signature_statuses`. Contains `slot`, `confirmations`, `err`, `confirmation_status`.
*   **`solders.transaction_status.TransactionConfirmationStatus`**: Enum indicating commitment level (`Processed`, `Confirmed`, `Finalized`).
*   **`solders.transaction.TransactionError`**: Base enum for errors that can occur during transaction processing *before* execution (e.g., sanitization errors). Defined in `solders.transaction`.
*   **Instruction Execution Errors**: Errors occurring *during* instruction execution are typically found within the `err` field of `TransactionStatus` or simulation results. They often follow this structure:
    *   `solders.transaction_status.TransactionErrorInstructionError(instruction_index: int, instruction_error: InstructionError)`: Indicates an error occurred in a specific instruction.
    *   **`InstructionError`**: This is the core enum for instruction-level errors. Key variants found in `solders.transaction_status`:
        *   `InstructionErrorFieldless`: Represents errors without specific data (e.g., `GenericError`, `InvalidArgument`, `InvalidInstructionData`, `AccountDataTooSmall`, `AccountNotExecutable`, `AccountBorrowFailed`, `AccountAlreadyBorrowed`, `InsufficientFunds`, `AccountInUse`). **Note:** `AccountInUse` is listed as a fieldless instruction error variant here.
        *   `InstructionErrorCustom(code: int)`: Program-specific error code.
        *   `InstructionErrorBorshIO(message: str)`: Error during Borsh deserialization within the program.

*   **Other `TransactionError` Variants** (from `solders.transaction_status`):
    *   `TransactionErrorDuplicateInstruction(index: int)`: An instruction index was duplicated.
    *   `TransactionErrorInsufficientFundsForRent(account_index: int)`: Account needs more lamports for rent exemption.

### Other Errors (`solders.errors.*`)

*   `solders.errors.SignerError`: Error related to transaction signing.
*   `solders.errors.BincodeError`, `solders.errors.CborError`, `solders.errors.SerdeJSONError`: Serialization/deserialization errors.