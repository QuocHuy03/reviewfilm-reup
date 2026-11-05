"""
CapCut TTS API Configuration & Defaults.
"""

BASE_URL = "https://editor-api-sg.capcutapi.com"
VOD_REGION = "sdwdmwlll"
VOD_SERVICE = "vod"
import random
device = str(random.randint(10**18, 10**19 - 1))   # device id ngẫu nhiên 19 số (khớp traffic CapCut PC thật)
# Profile CapCut PC 9.5.0 Windows — khớp traffic đã bắt (bản mac 8.7.0 cũ dễ bị xếp hàng / cắt câu).
DEFAULT_DEVICE = {
    "aid": "359289",
    "app_name": "CapCut",
    "appvr": "9.5.0",
    "version_name": "9.5.0",
    "version_code": "9.5.0",
    "channel": "capcutpc_0",
    "device_platform": "windows",
    "device_type": "",
    "device_brand": "American Megatrends Inc.",
    "os_version": "10.0.19045",
    "device_id": device,
    "iid": device,
    "region": "VN",
    "loc": "VN",
    "lan": "en",
    "pf": "4",
    "tdid": device,
} 

TTS_SIGN_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmTd34Lw4b7IuldSXh/zY
CMla+ITdGG5TeWz6ad+OySd4r+IrY45AoqrYUxhQ2dl+7z+i7r/5vEa8rr39BYfB
8AGMQLmZA8HmgpWBsqrn/V6daUALkKnkLb70Fn32CJigIuGXAYqxUdGuI340aC+0
v5Es3puJsHyzf01/AelE4Cdc6bZhQrASJLBh8R3BQToYClmDVSDUQk28o8sl/guA
Z4n303Vj+6Siv1HayPCdV6kpVVnMBAG4+umUbwGmn132N3fgpzLarFF3XyWmS1zh
D/J07iM/rP8GDO9IskHNHd2phrO0G6KzrcFAnTBHjVv+hCBEfzN/no3FNA9AuC36
mwIDAQAB
-----END PUBLIC KEY-----"""
