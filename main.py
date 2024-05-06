import os, re
import time
from collections import deque
import discord
from discord.ext import voice_recv
import vertexai
from vertexai.language_models import TextEmbeddingModel, TextGenerationModel
from dotenv import load_dotenv
from voicevox.speaker_info import SpeakerInfo
from youtube_dl import YoutubeDL
from typing import Optional, Tuple, Dict, Callable, Any
from voicevox import Client
from ko2kana import toKana
import speech_recognition as sr

load_dotenv()

vertexai.init(project=os.getenv("GCLOUD_PROJECT"), location=os.getenv("GCLOUD_LOCATION"))
parameters = {
    "candidate_count": 1,
    "max_output_tokens": 512,
    "temperature": 0.8,
    "top_k": 10,
    "top_p": 1
}
model = TextGenerationModel.from_pretrained("text-unicorn")

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
    	'key': 'FFmpegExtractAudio',
    	'preferredcodec': 'mp3',
    	'preferredquality': '192',
    }]  
}

guild: Optional[discord.Guild] = None
lock = False

voice_clients: dict[str, Optional[voice_recv.VoiceRecvClient]] = {}
vc_log: list[str] = []
user_context: dict[str, str] = {}

last_sent = 0

vclient = Client()

def rc_cb(recognizer: sr.Recognizer, audio: sr.AudioData, user: Any) -> Optional[str]:
    text: Optional[str] = None

    try:
        text = recognizer.recognize_google(audio, language="ko-KR")
    except sr.UnknownValueError:
        pass
    except sr.RequestError as e:
        print("Could not request results from Google Speech Recognition service; {0}".format(e))

    return text

class MyClient(discord.Client):
    async def on_ready(self):
        global guild

        guild = client.get_guild(731770334725799987)

        print(f'Logged on as {self.user}')

    async def on_message(self, ctx: discord.Message):
        global last_sent, lock, guild

        if str(guild.id) not in voice_clients:
            voice_clients[str(guild.id)] = None

        async def cmd(command: str):
            global voice_clients

            async def callback(user, text):
                log = '\n'.join(deque(vc_log, maxlen=5))

                text_input = f"""
**Persona:**
* 이름: "{self.user}"

**능력:**
* 사용자와 자연스럽고 친근한 대화를 나눌 수 있습니다.
* 그림을 생성하는 기능은 없습니다.

**지식:**
* 참가중인 음성 채널: #!{voice_clients[str(guild.id)].channel.name}
* 현자 날짜 및 시각: {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}

**추가 지침:**
* 자기소개를 금지합니다.
* 불법적, 외설적이거나 피해를 주는 채팅은 대답을 회피합니다.
* @everyone을 사용하지 않습니다.
* 필요할 경우 답변 맨 마지막 줄에 추가하여 사용합니다.
 * `!!join <username>`: 해당 유저의 음성 채팅방에 입장합니다.
 * `!!leave`: 음성채팅을 나갑니다.
 * `!!search <title>`: 음악을 검색합니다.
 * `!!play <index>`: 검색된 음악을 재생합니다.
 * `!!pause`: 음악을 일시정지합니다.
 * `!!resume`: 음악을 다시 재생합니다.
 * `!!stop`: 음악을 정지합니다.

예시:
Response: 통화방에 참여할게요

!!join <username>
---

**대화 기록:**
{log}

Response: """
                response = model.predict(text_input, **parameters)

                print(f'Input: {text_input}')
                print(f'{response.text}')

                res = re.sub(r"\n!!", "\n", response.text)
                print(f'filtered: {res}')

                kana = toKana(res).replace(" ", '')
                audio_query = await vclient.create_audio_query(
                    kana, speaker=8
                )
                with open("voice.wav", "wb") as f:
                    f.write(await audio_query.synthesis(speaker=8))


                for text in response.text.split('\n\n'):
                    text = text.strip('\n')
                    if text.startswith("!!"):
                        await cmd(text[2:])
                        continue

                player = voice_clients[str(guild.id)]

                player.play(discord.FFmpegPCMAudio("voice.wav"))

            def callback_wrapper(user, text):
                print(f"{user}: {text}")
                
                vc_log.append(f'{user}: {text}')
                
                self.loop.create_task(callback(user, text))

            instruction = command.split()

            user = discord.utils.get(guild.members, name=instruction[1])
            if user is None:
                user = ctx.author
            print(instruction)

            if instruction[0] == "join":
                vc_log = []
                voice_clients[str(guild.id)] = await user.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
                voice_clients[str(guild.id)].listen(voice_recv.extras.SpeechRecognitionSink(process_cb=rc_cb, text_cb=callback_wrapper))

            elif instruction[0] == "leave":
                print(voice_clients[str(guild.id)])
                await voice_clients[str(guild.id)].disconnect(force=False)

            elif instruction[0] == "search":
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch:{command[6:]}", download=False)['entries']
                    print(info)

            elif instruction[0] == "play":
                voice_clients[str(guild.id)] = await user.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
                voice_clients[str(guild.id)].listen(voice_recv.extras.SpeechRecognitionSink(process_cb=rc_cb, text_cb=callback))

            elif instruction[0] == "pause":
                if voice_clients[str(guild.id)].is_paused():
                    return
                
                voice_clients[str(guild.id)].pause()

            elif instruction[0] == "resume":
                if not voice_clients[str(guild.id)].is_paused():
                    return
                
                voice_clients[str(guild.id)].resume()

            elif instruction[0] == "stop":
                if not voice_clients[str(guild.id)].is_playing():
                    return
                
                voice_clients[str(guild.id)].stop()

        # 봇이 전송한 메시지일 경우 무시
        if ctx.author.bot:
            return
        
        # 특정 채팅 채널에서만 사용할 수 있도록 제한
        if ctx.channel.id != 1225034708971159643:
            return
        
        # 이미 채팅을 생성중일 경우 취소
        if lock:
            return
        
        lock = True
        
        user_ids = re.findall(r"<@!?(\d+)>", ctx.content)
        users = [ await client.fetch_user(user_id) for user_id in user_ids ]
        
        channel_ids = re.findall(r"<#(\d+)>", ctx.content)
        channels = [ await client.fetch_channel(channel_id) for channel_id in channel_ids ]

        emoji_ids = re.findall(r"<:(\w+):(\d+)>", ctx.content)

        # <@숫자> 형식을 <@유저명> 형식
        # <#숫자> 형식을 <#채널명> 형식으로 변환
        message_content = ctx.content
        for user in users:
            message_content = message_content.replace(f"<@{user.id}>", f"@{user.name}")
        for channel in channels:
            message_content = message_content.replace(f"<#{channel.id}>", f"#{channel.name}")

        chat_users = [ msg.author async for msg in ctx.channel.history(limit=7) ]
        vc_users = [ user for user in chat_users if hasattr(user, "voice") ]

        print(vc_users)
        chat_log = '\n'.join(reversed([f'{msg.author.name}: {msg.content}' async for msg in ctx.channel.history(limit=7)]))

        try:
            vc_name = "#!"+voice_clients[str(guild.id)].channel.name
            
            if vc_name is None:
                vc_name = "<연결되지 않음>"
        except:
            vc_name = "<연결되지 않음>"

# Prompt is also generated
        text_input = f"""
**Persona:**
* 이름: "{self.user}"

**능력:**
* 사용자와 자연스럽고 친근한 대화를 나눌 수 있습니다.
* 그림을 생성하는 기능은 없습니다.

**지식:**
* 참가중인 텍스트 채널: #{ctx.channel}
* 참가중인 음성 채널: {vc_name}
* 현자 날짜 및 시각: {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}

**추가 지침:**
* 자기소개를 금지합니다.
* 불법적, 외설적이거나 피해를 주는 채팅은 대답을 회피합니다.
* @everyone을 사용하지 않습니다.
* 필요할 경우 답변 맨 마지막 줄에 추가하여 사용합니다.
 * `!!join <username>`: 해당 유저의 음성 채팅방에 입장합니다.
 * `!!leave`: 음성채팅을 나갑니다.
 * `!!search <title>`: 음악을 검색합니다.
 * `!!play <index>`: 검색된 음악을 재생합니다.
 * `!!pause`: 음악을 일시정지합니다.
 * `!!resume`: 음악을 다시 재생합니다.
 * `!!stop`: 음악을 정지합니다.

예시:
Response: 통화방에 참여할게요

!!join <username>
---

**채팅 기록:**
{chat_log}

Response: """

        try:
            async with ctx.channel.typing():
                response = model.predict(text_input, **parameters)

                print(f'Input: {text_input}')
                print(f'{response.text}')

                for text in response.text.split('\n\n'):
                    text = text.strip('\n')
                    if text.startswith("!!"):
                        await cmd(text[2:])
                        continue

                    async with ctx.channel.typing():
                        time.sleep(0.75)
                    if '@everyone' in text:
                        raise ValueError()
                    await ctx.channel.send(text)
        except Exception as e:
            print(e)
            await ctx.channel.send(r"\*\*FILTERED\*\*")
            lock = False

        last_sent = time.time()
        lock = False

intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)
client.run(os.getenv("DISCORD_TOKEN"))