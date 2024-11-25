import unittest
from unittest.mock import patch, MagicMock
from main import app, context_storage
import json

class TestChatAPI(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_missing_api_key(self):
        """测试缺少 API key 的情况"""
        response = self.app.get('/?model_type=openai&model=gpt-3.5-turbo&input=test')
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'API key is required')

    def test_invalid_model_type(self):
        """测试无效的模型类型"""
        response = self.app.get(
            '/?model_type=invalid&model=test&input=test',
            headers={'Authorization': 'test_key'}
        )
        self.assertEqual(response.status_code, 400)

    @patch('main.ChatOpenAI')
    def test_openai_chat(self, mock_chat):
        """测试 OpenAI 聊天功能"""
        # 模拟 ChatOpenAI 的响应
        mock_instance = MagicMock()
        mock_chat.return_value = mock_instance
        mock_instance.stream.return_value = [
            MagicMock(content='Hello'),
            MagicMock(content=' World')
        ]

        with self.app as client:
            response = client.get(
                '/?model_type=openai&model=gpt-3.5-turbo&input=test&id=123',
                headers={'Authorization': 'test_key'}
            )
            
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'text/event-stream')

            # 读取并验证流式响应
            response_data = list(response.response)
            self.assertTrue(any(b'Hello' in data for data in response_data))
            self.assertTrue(any(b'World' in data for data in response_data))

    @patch('main.ChatAnthropic')
    def test_claude_chat(self, mock_chat):
        """测试 Claude 聊天功能"""
        mock_instance = MagicMock()
        mock_chat.return_value = mock_instance
        mock_instance.stream.return_value = [
            MagicMock(content='Hello from Claude')
        ]

        with self.app as client:
            response = client.get(
                '/?model_type=claude&model=claude-3-opus-20240229&input=test&id=123',
                headers={'Authorization': 'test_key'}
            )
            
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'text/event-stream')

            # 读取并验证流式响应
            response_data = list(response.response)
            self.assertTrue(any(b'Hello from Claude' in data for data in response_data))

    def test_context_storage(self):
        """测试上下文存储功能"""
        with patch('main.ChatOpenAI') as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance
            mock_instance.stream.return_value = [MagicMock(content='Test Response')]

            with self.app as client:
                # 第一次请求，设置上下文
                response1 = client.get(
                    '/?model_type=openai&model=gpt-3.5-turbo&input=test&content_id=test_context',
                    headers={'Authorization': 'test_key'}
                )
                self.assertEqual(response1.status_code, 200)

                # 消费完第一个响应的内容
                list(response1.response)

                # 第二次请求，验证上下文是否存在
                response2 = client.get(
                    '/?model_type=openai&model=gpt-3.5-turbo&input=test2&content_id=test_context',
                    headers={'Authorization': 'test_key'}
                )
                self.assertEqual(response2.status_code, 200)
                
                # 消费完第二个响应的内容
                list(response2.response)

            # 验证上下文是否被正确存储和使用
            self.assertIn('test_context', context_storage)
            self.assertIn('test', context_storage['test_context'])
            self.assertIn('test2', context_storage['test_context'])

    def test_proxy_setting(self):
        """测试代理设置功能"""
        with patch('main.ChatOpenAI') as mock_chat:
            mock_instance = MagicMock()
            mock_chat.return_value = mock_instance
            mock_instance.stream.return_value = [MagicMock(content='Test')]

            with self.app as client:
                response = client.get(
                    '/?model_type=openai&model=gpt-3.5-turbo&input=test',
                    headers={
                        'Authorization': 'test_key',
                        'Agent': 'http://proxy.example.com'
                    }
                )
                self.assertEqual(response.status_code, 200)

    @patch('main.ZhipuAI')
    def test_zhipu_chat(self, mock_zhipu):
        """测试智谱 AI 聊天功能"""
        mock_instance = MagicMock()
        mock_zhipu.return_value = mock_instance
        test_response = 'ZhipuAI response'  # 使用英文替代中文
        mock_instance.chat.completions.create.return_value = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content=test_response))])
        ]

        with self.app as client:
            response = client.get(
                '/?model_type=zhipu&model=glm-4&input=test&id=123',
                headers={'Authorization': 'test_key'}
            )
            
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'text/event-stream')

            # 读取并验证流式响应
            response_data = list(response.response)
            self.assertTrue(any(test_response.encode() in data for data in response_data))

if __name__ == '__main__':
    unittest.main() 