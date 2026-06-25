# 04 — Channel System

> Channel abstraction, 17 built-in channels, ChannelManager, message routing.

---

## BaseChannel (ABC)

```python
class BaseChannel(ABC):
    channel: ChannelType                    # class attr, e.g. "discord"
    
    @classmethod
    def from_config(cls, config) -> Self:   # factory
        ...
    
    @classmethod
    def from_env(cls) -> Self:              # factory
        ...
    
    async def start() -> None:              # lifecycle
        ...
    
    async def stop() -> None:               # lifecycle
        ...
    
    @abstractmethod
    async def consume_one(payload) -> None: # process message
        ...
```

---

## 17 Built-in Channels

| Channel | Type | Protocol |
|---------|------|----------|
| `console` | Web UI | HTTP + SSE |
| `discord` | IM | Discord API |
| `dingtalk` | IM | DingTalk Stream |
| `feishu` | IM | Lark/Feishu API |
| `qq` | IM | QQ Bot |
| `telegram` | IM | Telegram Bot API |
| `mattermost` | Team Chat | Mattermost API |
| `mqtt` | IoT | MQTT protocol |
| `matrix` | Federation | Matrix/nio |
| `voice` | Audio | Twilio Voice |
| `sip` | VoIP | SIP protocol |
| `wecom` | IM | WeCom Bot |
| `xiaoyi` | IM | XiaoYi |
| `wechat` | IM | WeChat Official Account |
| `onebot` | IM | OneBot standard |
| `imessage` | Apple | iMessage |
| `custom` | Any | User-defined from `CUSTOM_CHANNELS_DIR` |

---

## ChannelManager

```
ChannelManager
    ├── UnifiedQueueManager ──► per-channel asyncio.Queue
    ├── Consumer loops ──► asyncio.Tasks
    ├── from_config() ──► reads config.json → channels
    └── _process_batch() ──► merge multi-message → consume_one()
```

### Message Flow

```
External Platform (Discord, Telegram, etc.)
    │
    ▼
Channel-specific adapter
    │
    ▼
ChannelManager.enqueue(channel_id, payload)   [thread-safe]
    │
    ▼
UnifiedQueueManager ──► asyncio.Queue
    │
    ▼
Consumer loop ──► _process_batch()
    │
    ▼
BaseChannel.consume_one(payload)
    │
    ▼
Workspace.runner.stream_query(request)
```

---

## Channel Registry

```python
class ChannelRegistry:
    # Thread-safe cache of built-in + custom channel classes
    # Lazy-loaded on first access
    
    @classmethod
    def get_registry() -> ChannelRegistry: ...
    
    def keys() -> list[str]: ...
    def get(key: str) -> type[BaseChannel]: ...
```

**Discovery**:
1. Built-in channels from `src/openspider/app/channels/<name>/channel.py`
2. Custom channels from `CUSTOM_CHANNELS_DIR` (configurable)
3. Entry point group `openspider.channels`

---

## Custom Channels

Users can add custom channels by placing a Python module in `CUSTOM_CHANNELS_DIR`:

```python
# custom_channels/my_bot.py
from openspider.app.channels.base import BaseChannel
from openspider.app.channels.schema import ChannelType

class MyBotChannel(BaseChannel):
    channel: ChannelType = "my_bot"
    
    async def consume_one(self, payload) -> None:
        # Process incoming message
        ...
```

Managed via CLI:
```bash
openspider channels install <key>
openspider channels add <key>
openspider channels remove <key>
openspider channels config
```
