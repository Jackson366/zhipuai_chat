import json
import os
import uuid
from datetime import datetime
from openai import OpenAI
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.exception import AppwriteException

def main(context):
    """
    Appwrite Function主入口，实现OpenAI流式聊天功能
    """
    try:
        # 解析请求数据
        payload = json.loads(context.req.body or '{}')
        
        # 获取环境变量
        openai_api_key = os.environ.get('OPENAI_API_KEY', '63d72f1ffdad498380426cf9fea99783.lGPa6l8kl9ZXlYkO')
        openai_base_url = os.environ.get('OPENAI_BASE_URL', 'https://open.bigmodel.cn/api/paas/v4/')
        appwrite_api_key = os.environ.get('APPWRITE_API_KEY', '6801f3ee0031c2b7ac4d')
        appwrite_endpoint = os.environ.get('APPWRITE_ENDPOINT', 'https://nyc.cloud.appwrite.io/v1')
        database_id = os.environ.get('DATABASE_ID', '6803573d00249e9a00d8')
        collection_id = os.environ.get('COLLECTION_ID', '6804b7c60030725577bb')
        
        if not openai_api_key:
            return context.res.json({
                'error': 'OPENAI_API_KEY environment variable is required'
            }, 400)
        
        # 初始化OpenAI客户端
        client = OpenAI(api_key=openai_api_key, base_url=openai_base_url)
        
        # 获取聊天参数
        messages = payload.get('messages', [])
        model = payload.get('model', 'glm-4-air')
        temperature = payload.get('temperature', 0.7)
        max_tokens = payload.get('max_tokens', 1240)
        stream = payload.get('stream', True)
        user_id = payload.get('userId')
        conv_id = payload.get('convId')
        
        if not messages:
            return context.res.json({
                'error': 'Messages array is required'
            }, 400)
        
        # 初始化Appwrite客户端，用于存储聊天历史
        appwrite_client = None
        if database_id and collection_id:
            appwrite_client = Client()
            appwrite_client.set_endpoint(appwrite_endpoint).set_key(appwrite_api_key)
            databases = Databases(appwrite_client)
        
        # 如果启用流式响应
        if stream:
            return handle_stream_chat(context, client, messages, model, temperature, max_tokens, 
                                     databases if appwrite_client else None, database_id, collection_id, user_id, conv_id)
        else:
            return handle_normal_chat(context, client, messages, model, temperature, max_tokens,
                                     databases if appwrite_client else None, database_id, collection_id, user_id, conv_id)
            
    except json.JSONDecodeError:
        return context.res.json({
            'error': 'Invalid JSON in request body'
        }, 400)
    except Exception as e:
        context.log(f"Error: {str(e)}")
        return context.res.json({
            'error': f'Internal server error: {str(e)}'
        }, 500)

def save_chat_history(databases, database_id, collection_id, user_id, conv_id, role, content):
    """
    保存聊天历史到Appwrite数据库
    """
    if not (databases and database_id and collection_id):
        return None
    
    try:
        # 如果没有提供会话ID，生成一个新的
        if not conv_id:
            conv_id = str(uuid.uuid4())
            
        # 准备要存储的文档数据
        document_data = {
            'userId': user_id or 'anonymous',
            'role': role,
            'content': content,
            'convId': conv_id
        }
        
        # 创建文档
        document = databases.create_document(
            database_id=database_id,
            collection_id=collection_id,
            document_id='unique()',
            data=document_data
        )
        
        return conv_id
    except AppwriteException as e:
        print(f"Appwrite Error: {str(e)}")
        return None
    except Exception as e:
        print(f"Error saving chat history: {str(e)}")
        return None

def handle_stream_chat(context, client, messages, model, temperature, max_tokens, 
                     databases=None, database_id=None, collection_id=None, user_id=None, conv_id=None):
    """
    处理流式聊天响应
    """
    try:
        # 设置响应头为Server-Sent Events
        context.res.headers['Content-Type'] = 'text/event-stream'
        context.res.headers['Cache-Control'] = 'no-cache'
        context.res.headers['Connection'] = 'keep-alive'
        context.res.headers['Access-Control-Allow-Origin'] = '*'
        
        # 保存用户消息
        last_user_message = next((msg for msg in reversed(messages) if msg['role'] == 'user'), None)
        if last_user_message and databases:
            conv_id = save_chat_history(
                databases, database_id, collection_id, 
                user_id, conv_id, 'user', last_user_message['content']
            )
        
        # 创建流式聊天完成
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True
        )
        
        # 收集完整响应用于日志记录
        full_response = ""
        
        # 流式发送数据
        response_text = ""
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                full_response += content
                
                # 发送SSE格式的数据
                sse_data = json.dumps({
                    'type': 'content',
                    'content': content,
                    'done': False
                })
                response_text += f"data: {sse_data}\n\n"
        
        # 保存AI回复到历史记录
        if databases and full_response:
            conv_id = save_chat_history(
                databases, database_id, collection_id, 
                user_id, conv_id, 'assistant', full_response
            )
        
        # 发送完成信号，包含会话ID
        final_data = json.dumps({
            'type': 'done',
            'content': '',
            'done': True,
            'full_response': full_response,
            'convId': conv_id
        })
        response_text += f"data: {final_data}\n\n"
        
        return context.res.send(response_text, 200)
        
    except Exception as e:
        error_data = json.dumps({
            'type': 'error',
            'error': str(e),
            'done': True
        })
        return context.res.send(f"data: {error_data}\n\n", 500)

def handle_normal_chat(context, client, messages, model, temperature, max_tokens,
                     databases=None, database_id=None, collection_id=None, user_id=None, conv_id=None):
    """
    处理普通聊天响应
    """
    try:
        # 保存用户消息
        last_user_message = next((msg for msg in reversed(messages) if msg['role'] == 'user'), None)
        if last_user_message and databases:
            conv_id = save_chat_history(
                databases, database_id, collection_id, 
                user_id, conv_id, 'user', last_user_message['content']
            )
        
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False
        )
        
        assistant_response = response.choices[0].message.content
        
        # 保存AI回复到历史记录
        if databases and assistant_response:
            conv_id = save_chat_history(
                databases, database_id, collection_id, 
                user_id, conv_id, 'assistant', assistant_response
            )
        
        return context.res.json({
            'success': True,
            'response': assistant_response,
            'usage': {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            },
            'convId': conv_id
        })
        
    except Exception as e:
        return context.res.json({
            'error': str(e)
        }, 500)