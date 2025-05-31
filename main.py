import json
import os
from openai import OpenAI
from appwrite.client import Client
from appwrite.services.databases import Databases

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
        appwrite_api_key = os.environ.get('APPWRITE_API_KEY')
        appwrite_endpoint = os.environ.get('APPWRITE_ENDPOINT', 'https://cloud.appwrite.io/v1')
        

        

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
        
        if not messages:
            return context.res.json({
                'error': 'Messages array is required'
            }, 400)
        
        # 如果启用流式响应
        if stream:
            return handle_stream_chat(context, client, messages, model, temperature, max_tokens)
        else:
            return handle_normal_chat(context, client, messages, model, temperature, max_tokens)
            
    except json.JSONDecodeError:
        return context.res.json({
            'error': 'Invalid JSON in request body'
        }, 400)
    except Exception as e:
        context.log(f"Error: {str(e)}")
        return context.res.json({
            'error': f'Internal server error: {str(e)}'
        }, 500)

def handle_stream_chat(context, client, messages, model, temperature, max_tokens):
    """
    处理流式聊天响应
    """
    try:
        # 设置响应头为Server-Sent Events
        context.res.headers['Content-Type'] = 'text/event-stream'
        context.res.headers['Cache-Control'] = 'no-cache'
        context.res.headers['Connection'] = 'keep-alive'
        context.res.headers['Access-Control-Allow-Origin'] = '*'
        
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
        
        # 发送完成信号
        final_data = json.dumps({
            'type': 'done',
            'content': '',
            'done': True,
            'full_response': full_response
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

def handle_normal_chat(context, client, messages, model, temperature, max_tokens):
    """
    处理普通聊天响应
    """
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False
        )
        
        return context.res.json({
            'success': True,
            'response': response.choices[0].message.content,
            'usage': {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            }
        })
        
    except Exception as e:
        return context.res.json({
            'error': str(e)
        }, 500)