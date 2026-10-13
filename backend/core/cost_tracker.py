
"""
Chi phi API per video — track tokens va tinh VND.
Su dung qua CostAccumulator; module translator/vision analyzer tich luy,
main.py log summary cuoi moi video.
"""
import threading
_VND_PER_USD = 25800
_cost_tls = threading.local()
_PRICING = {'deepseek_in': 0.27, 'deepseek_out': 1.1, 'openai_in': 0.15, 'openai_out': 0.6}
class CostAccumulator:
    'Thu thap token usage tu tat ca API call trong 1 video run. Thread-safe.'
    def __init__(self):
        self._lock = threading.Lock()
        self._ds_in = 0
        self._ds_out = 0
        self._oai_in = 0
        self._oai_out = 0
        self._gem_calls = 0
        self._engines_used = set()
    def add_deepseek(self, in_tok, out_tok):
        with self._lock:
            self._ds_in += in_tok
            self._ds_out += out_tok
            if in_tok or out_tok:
                self._engines_used.add('DeepSeek')
    def add_openai(self, in_tok, out_tok, label='OpenAI'):
        with self._lock:
            self._oai_in += in_tok
            self._oai_out += out_tok
            if in_tok or out_tok:
                self._engines_used.add(label)
    def add_gemini(self, calls=1):
        with self._lock:
            self._gem_calls += calls
            if calls:
                self._engines_used.add('Gemini')
    def total_usd(self):
        ds = (self._ds_in * _PRICING['deepseek_in'] + self._ds_out * _PRICING['deepseek_out']) / 1000000
        oai = (self._oai_in * _PRICING['openai_in'] + self._oai_out * _PRICING['openai_out']) / 1000000
        return ds + oai
    def total_vnd(self):
        return int(self.total_usd() * _VND_PER_USD)
    def summary(self):
        lines = ['── CHI PHI API VIDEO NAY ─────────────────']
        if self._ds_in or self._ds_out:
            usd = (self._ds_in * _PRICING['deepseek_in'] + self._ds_out * _PRICING['deepseek_out']) / 1000000
            lines.append(f'''  DeepSeek : {self._ds_in:>7,} in + {self._ds_out:>7,} out tok  ≈  ${usd:.4f}  (~{int(usd * _VND_PER_USD):,}d)''')
        if self._oai_in or self._oai_out:
            usd = (self._oai_in * _PRICING['openai_in'] + self._oai_out * _PRICING['openai_out']) / 1000000
            lines.append(f'''  OpenAI   : {self._oai_in:>7,} in + {self._oai_out:>7,} out tok  ≈  ${usd:.4f}  (~{int(usd * _VND_PER_USD):,}d)''')
        if self._gem_calls:
            lines.append(f'''  Gemini   : {self._gem_calls} lan goi  →  MIEN PHI (free tier)''')
        t_usd = self.total_usd()
        t_vnd = self.total_vnd()
        if t_usd > 0:
            lines.append(f'''  TONG     : ${t_usd:.4f}  (~{t_vnd:,}d / video nay)''')
        elif self._gem_calls:
            lines.append('  TONG     : 0d  (chi dung Gemini FREE)')
        else:
            lines.append('  TONG     : 0d  (khong goi API tra phi)')
        if self._engines_used:
            lines.append(f'''  Engine   : {', '.join(sorted(self._engines_used))}''')
        lines.append('──────────────────────────────────────────')
        return '\n'.join(lines)