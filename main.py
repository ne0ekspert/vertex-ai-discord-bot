import os, re
import time
import discord
import vertexai
from vertexai.language_models import TextEmbeddingModel, TextGenerationModel

from dotenv import load_dotenv

load_dotenv()

vertexai.init(project=os.getenv("GCLOUD_PROJECT"), location=os.getenv("GCLOUD_LOCATION"))
parameters = {
    "candidate_count": 1,
    "max_output_tokens": 512,
    "temperature": 0.8,
    "top_k": 10
}
model = TextGenerationModel.from_pretrained("text-unicorn@001")

lock = False
last_sent = 0

class MyClient(discord.Client):
    async def on_ready(self):
        print(f'Logged on as {self.user}')

    async def on_message(self, message):
        global last_sent, lock

        # 봇이 전송한 메시지일 경우 무시
        if message.author.bot:
            return
        
        # 특정 채팅 채널에서만 사용할 수 있도록 제한
        if message.channel.id != 1225034708971159643:
            return
        
        # 이미 채팅을 생성중일 경우 취소
        if lock:
            return
        
        lock = True
        
        user_ids = re.findall(r"<@!?(\d+)>", message.content)
        users = [await client.fetch_user(user_id) for user_id in user_ids]
        
        channel_ids = re.findall(r"<#(\d+)>", message.content)
        channels = [await client.fetch_channel(channel_id) for channel_id in channel_ids]

        emoji_ids = re.findall(r"<:(\w+):(\d+)>", message.content)

        message_content = message.content
        for user in users:
            message_content = message_content.replace(f"<@{user.id}>", f"@{user.name}")
        for channel in channels:
            message_content = message_content.replace(f"<#{channel.id}>", f"#{channel.name}")
        
        chat_log = '\n'.join(reversed([f'{msg.author.name}: {msg.content}' async for msg in message.channel.history(limit=7)]))
# Prompt is also generated
        text_input = f"""
**Persona:**
* 이름: "{self.user}"

**능력:**
* 사용자와 자연스럽고 매력적인 대화를 나눌 수 있습니다.
* 다양한 주제에 대한 질문에 답변할 수 있습니다.
* 스스로 이야기를 이끌어갈 수 있습니다.
* 새로운 정보를 배우고 적응할 수 있습니다.
* 창의적인 텍스트 형식을 생성할 수 있습니다.
* 채팅의 흐름에 맞춰 대답할 수 있습니다.
* 그림을 생성하는 기능은 없습니다.
* 음성 인식을 하거나, 음성 채팅방에 입장할 수 있는 기능은 없습니다.

**지식:**
* 현재 채팅 채널명: #{message.channel}
* 현자 날짜 및 시각: {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())}

**추가 지침:**
* 채팅의 흐름에 맞게 대답을 합니다.
* 다른 사람을 사칭하지 않습니다.
* 자기소개를 금지합니다.
* 불법적, 외설적이거나 피해를 주는 채팅은 대답을 회피합니다.
* 대답을 2문장 정도 짧게 합니다.
* 이야기의 주인공이 본인이 언급한 사실이 아니면 믿지 않습니다.
* @everyone을 사용하지 않습니다.

**채팅 기록:**
{chat_log}

**Response:**
{self.user}: """

        try:
            async with message.channel.typing():
                response = model.predict(text_input, **parameters)

                print(f'Input: {text_input}')
                print(f'{response.text}')

                for text in response.text.split('\n\n'):
                    async with message.channel.typing():
                        time.sleep(0.75)
                    if '@everyone' in text:
                        raise ValueError()
                    await message.channel.send(text)
        except:
            await message.channel.send(r"\*\*FILTERED\*\*")
            lock = False

        last_sent = time.time()
        lock = False

intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)
client.run(os.getenv("DISCORD_TOKEN"))