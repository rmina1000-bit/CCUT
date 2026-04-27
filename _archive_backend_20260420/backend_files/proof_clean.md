### 1. [Qwen3ASR DEBUG] raw= First 3 Lines
```text
[Qwen3ASR DEBUG] raw={'choices': [{'finish_reason': 'stop', 'index': 0, 'message': {'role': 'assistant', 'content': 'language Korean<asr_text>  ϰ ׷ ſ.'}}], 'created': 1776570459, 'model': 'Qwen3-ASR-0.6B-Q8_0.gguf', 'system_fingerprint': 'b8838-23b8cc499', 'object': 'chat.completion', 'usage': {'completion_tokens': 17, 'prompt_tokens': 402, 'total_tokens': 419, 'prompt_tokens_details': {'cached_tokens': 0}}, 'id': 'chatcmpl-LKkVbLEoWzQokLAtm9ElGR4eVnLNi94i', 'timings': {'cache_n': 0, 'prompt_n': 402, 'prompt_ms': 2919.822, 'prompt_per_token_ms': 7.26323880597015, 'prompt_per_second': 137.67962567581174, 'predicted_n': 17, 'predicted_ms': 450.568, 'predicted_per_token_ms': 26.503999999999998, 'predicted_per_second': 37.73015393902807}}
[Qwen3ASR DEBUG] raw={'choices': [{'finish_reason': 'stop', 'index': 0, 'message': {'role': 'assistant', 'content': 'language None<asr_text>'}}], 'created': 1776570469, 'model': 'Qwen3-ASR-0.6B-Q8_0.gguf', 'system_fingerprint': 'b8838-23b8cc499', 'object': 'chat.completion', 'usage': {'completion_tokens': 4, 'prompt_tokens': 402, 'total_tokens': 406, 'prompt_tokens_details': {'cached_tokens': 0}}, 'id': 'chatcmpl-C6Qa2XPWc8nxwwhAD8AKt7WbhCIuPX4Q', 'timings': {'cache_n': 0, 'prompt_n': 402, 'prompt_ms': 2904.198, 'prompt_per_token_ms': 7.224373134328358, 'prompt_per_second': 138.42031431741225, 'predicted_n': 4, 'predicted_ms': 88.503, 'predicted_per_token_ms': 22.12575, 'predicted_per_second': 45.1962080381456}}
[Qwen3ASR DEBUG] raw={'choices': [{'finish_reason': 'stop', 'index': 0, 'message': {'role': 'assistant', 'content': 'language Chinese<asr_text>ҸӴ . ̰  .'}}], 'created': 1776570561, 'model': 'Qwen3-ASR-0.6B-Q8_0.gguf', 'system_fingerprint': 'b8838-23b8cc499', 'object': 'chat.completion', 'usage': {'completion_tokens': 18, 'prompt_tokens': 402, 'total_tokens': 420, 'prompt_tokens_details': {'cached_tokens': 0}}, 'id': 'chatcmpl-73JQ26e7w2iuB4KvfWHxhss1fhfQ1YDl', 'timings': {'cache_n': 0, 'prompt_n': 402, 'prompt_ms': 2802.56, 'prompt_per_token_ms': 6.971542288557214, 'prompt_per_second': 143.44028316967345, 'predicted_n': 18, 'predicted_ms': 465.43, 'predicted_per_token_ms': 25.857222222222223, 'predicted_per_second': 38.673914444707044}}
```
### 2. DB Query json_extract
```text
ID: VF1_SRC_36482548 | Transcript: 
ID: VF2_SRC_36482548 | Transcript: 
ID: VF3_SRC_36482548 | Transcript: language Korean<asr_text>참모텔 다 제작하고 그러는 거예요.
ID: VF4_SRC_36482548 | Transcript: 
ID: VF5_SRC_36482548 | Transcript: 
```
### 3. tasklist llama-server
```text
llama-server.exe             20476 Console                    1  3,457,880 K
```