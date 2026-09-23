from aiogram.fsm.storage.memory import MemoryStorage

# Shared FSM storage for all owner bots in this process.
# For multi-worker deploy later: switch to Redis storage.
fsm_storage = MemoryStorage()
