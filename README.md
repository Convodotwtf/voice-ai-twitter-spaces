# 🚀 Convo.wtf - The Revolutionary Voice AI That Built a Global Cult

> **"The most powerful Twitter Spaces AI tool ever created - now yours to run locally"**

[![Windows Only](https://img.shields.io/badge/Platform-Windows%20Only-blue?style=for-the-badge&logo=windows)](https://windows.com)
[![AI Powered](https://img.shields.io/badge/AI-Powered%20by%20Convo-orange?style=for-the-badge&logo=robot)](https://convo.wtf)
[![Exclusive Access](https://img.shields.io/badge/Access-Exclusive%20Release-red?style=for-the-badge&logo=lock)](https://convo.wtf)

## 🌟 The Legend Behind Convo AI

**This isn't just another AI tool - this is the weapon that the convo.wtf team used to conquer the digital world.**

Convo AI was the secret sauce behind one of the most viral AI phenomena in web3 history. While others were building basic chatbots, the convo team was crafting an AI that could hold conversations so natural, so engaging, that it built a cult following across every twitter space it joined.

### 🏆 Recognition That Speaks Volumes

Convo AI gained recognition from some of the biggest names in tech and web3:

- [Anatoly Yakovenko (Solana founder)](https://x.com/aeyakovenko/status/1887559911095377952?s=46)  
- [Jesse Pollak (creator of Coinbase’s L2 Base)](https://x.com/jessepollak/status/1894193080493887551?s=46)  
- [Robert Scoble](https://x.com/scobleizer/status/1874956559937384450?s=46)  
- [Elon Musk (reposted Robert Scoble’s post about Convo)](https://x.com/elonmusk/status/1893826073235775619?s=46)  
- **ElevenLabs** — Acknowledged Convo's voice with honorary Voice ID: `1SM7GgM6IMuvQlz2BwM3`

**The convo team had exclusive access to this technology. Now, for the first time ever, it's yours to run locally.**

## Requirements
- **OS**: Windows 10/11 (64-bit)
- **Python**: 3.9+
- **RAM**: 8GB+ (16GB+ recommended)
- **Dependencies**: Git, WSL2, VB-Cable, FFmpeg
- **Internet**: Required

## API Keys
- `OPENAI_API_KEY` – GPT-4
- `GOOGLE_APPLICATION_CREDENTIALS` – Google Speech-to-Text JSON path
- `XI_API_KEY` – ElevenLabs
- `X_API_KEY`, `X_API_SECRET`, `X_BEARER_TOKEN` – Twitter

## Install
```bash
git clone https://github.com/Convodotwtf/voice-ai-twitter-spaces.git
cd voice-ai-twitter-spaces
pip install -r requirements.lock
cp .env.example .env
# Edit .env with your keys
Run
bash
Copy
Edit
# Default mic/speakers
python -m src.convo_backend.app --device default

# VB-Cable routing
python -m src.convo_backend.app --device cables

# Debug mode
python -m src.convo_backend.app --debug

# Auto join Spaces
python -m src.convo_backend.app --roaming
Audio Setup
Install VB-Cable

Set CABLE Input as default playback

Set CABLE Output as default recording

Customization
Edit src/convo_backend/assets/default_prompt.txt for personality

Adjust voice settings in GUI

Troubleshooting
Missing modules → pip install -r requirements.lock

API errors → Check .env

No audio → Reinstall VB-Cable, verify Windows sound settings

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

---

**Love from the convo.wtf team** ❤️

*"We built this to change the world. Now it's your turn."*

---

**⚠️ Disclaimer**: This tool is for educational and entertainment purposes. Use responsibly and respect platform terms of service. The convo.wtf team is not responsible for how you use this technology. For full Token disclaimer, visit [convo.wtf/disclaimer](https://convo.wtf/disclaimer).
