# Solana.py and Solders API Reference Summary

This document summarizes key API details, type definitions, and error structures from `solana-py` and `solders`, focusing on aspects relevant to RPC interactions, transaction handling, and common error types based on the provided documentation URLs and recent findings.

**Note:** Core types previously in `solana-py` have largely moved to the `solders` library. `solana-py` now uses `solders` extensively under the hood. **Modern usage strongly favors `VersionedTransaction` over the legacy `Transaction` type.**

## Solana.py (`solana` package)

Provides the Python SDK for interacting with the Solana JSON RPC API and includes helpers for SPL interactions.

### RPC Client (`solana.rpc.api.Client` / `solana.rpc.async_api.AsyncClient`)

Used for making synchronous/asynchronous calls to the Solana RPC endpoint.

**Key Methods:**

*   `send_transaction(txn: Union[VersionedTransaction, Transaction], opts: Optional[TxOpts]) -> SendTransactionResp`: Sends a signed transaction. Performs preflight checks by default. **Prefers `VersionedTransaction`**.
*   `confirm_transaction(tx_sig: Signature, commitment: Optional[Commitment], ...) -> GetSignatureStatusesResp`: Polls the network to confirm a transaction signature reaches a specified commitment level.
*   `simulate_transaction(txn: Union[Transaction, VersionedTransaction], ...) -> SimulateTransactionResp`: Simulates a transaction without sending it to the network. Useful for checking potential errors and estimating compute units. **Prefers `VersionedTransaction`**.
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

*   `solana.rpc.core.RPCException`: General exception for RPC errors returned by the node. The error payload often contains more specific details. Can wrap `solders.rpc.errors.SendTransactionPreflightFailureMessage`.
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
*   `solders.message.Message`: Legacy message format.
*   `solders.message.MessageV0`: **Recommended message format.** Supports Address Lookup Tables (ALT).
    *   `MessageV0.try_compile(payer: Pubkey, instructions: List[Instruction], address_lookup_table_accounts: List[MessageAddressTableLookup], recent_blockhash: Hash) -> MessageV0`: Compiles instructions, payer, LUTs, and blockhash into a `MessageV0`.
*   `solders.transaction.Transaction`: Legacy transaction format. **Avoid if possible.**
*   `solders.transaction.VersionedTransaction`: **Recommended transaction type.** Wrapper for different transaction versions (Legacy or V0).
    *   Constructor: `VersionedTransaction(message: Union[Message, MessageV0], keypairs: List[Keypair])`. Takes the compiled message and a list of all required signers (Keypair objects). Handles signing internally.

### RPC Related Types (`solders.rpc.*`)

Contains types used for building RPC requests and parsing responses (used by `solana-py`). Includes request/response structures, configuration objects (`CommitmentConfig`), filters (`RpcFilterType`), etc.

*   `solders.rpc.errors.SendTransactionPreflightFailureMessage`: Specific error type often wrapped by `RPCException` when simulation fails. Contains details about the underlying `TransactionError`.
    *   Constructor likely takes the `TransactionError` object via a `message=` keyword argument (based on recent test failures, though documentation is unclear).

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
*   **`solders.transaction.TransactionError`**: Base enum for errors that can occur during transaction processing *before* execution (e.g., sanitization errors). Defined in `solders.transaction`. **Does not accept keyword arguments in constructor.**
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

### Example: Sending SOL with `VersionedTransaction` (Based on Tutorial)

```python
from solders.hash import Hash
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.system_program import TransferParams, transfer
from solders.transaction import VersionedTransaction
from solders.pubkey import Pubkey # Added for clarity

# Assume sender and receiver are Keypair objects, blockhash is a valid Hash
sender: Keypair = ...
receiver_pubkey: Pubkey = ...
lamports_to_send: int = 1_000_000
blockhash: Hash = ... # Fetched via get_latest_blockhash

# 1. Create Instruction
ix = transfer(
    TransferParams(
        from_pubkey=sender.pubkey(),
        to_pubkey=receiver_pubkey,
        lamports=lamports_to_send
    )
)

# 2. Compile MessageV0
msg = MessageV0.try_compile(
    payer=sender.pubkey(),
    instructions=[ix], # Include compute budget instructions if needed
    address_lookup_table_accounts=[], # Add LUTs if using them
    recent_blockhash=blockhash,
)

# 3. Create and Sign VersionedTransaction
# Pass the message and a list of ALL required signers (Keypair objects)
tx = VersionedTransaction(msg, [sender])

# 4. Send (using solana-py client)
# client: AsyncClient = ...
# await client.send_transaction(tx, opts=...)