__doc__ = '\nTranslator — Dich & Reup pipeline (phien ban 3 — PIVOT qua tieng Anh):\n  1. Gom Whisper segments thanh blocks ~10-12s (bao toan ngu canh)\n  2. Phan tich ngu canh phim → glossary KHOA CUNG ten rieng/thuat ngu (chong pivot lam hong Han-Viet)\n  3. Stage A: dich goc(Trung...) → TIENG ANH trung gian (hieu DUNG nghia, het mo ho)\n  4. Stage B: dich tieng Anh + doi chieu ban goc + glossary → TIENG VIET dia phuong hoa muot\n  5. Stage C: ChatGPT "nuot" ngu dieu giong thuyet minh YouTube VN\n  6. Tra ve list scenes cho TTS + video editor\n\nVi sao pivot qua tieng Anh: tieng Anh lam ro nghia (tri "sai nghia"), con glossary giu\nten rieng/thuat ngu di THANG Han-Viet (giang ho, Truong Tam...) — khong bi pivot pha nat.\nKhong co API key: Google dich pivot goc→Anh→Viet (don thuan, khong nuot).\n'
import os, time, json, re, requests
BLOCK_MAX_DUR = 12.0
BLOCK_MAX_CHARS = 220
BATCH_BLOCKS = 80
FILM_TITLE_VI_DICT = {'鬼吹灯': 'Ma Thổi Đèn', 'ghost blows out the light': 'Ma Thổi Đèn', '鬼吹灯之精绝古城': 'Ma Thổi Đèn: Tinh Tuyệt Cổ Thành', '鬼吹灯之黄皮子坟': 'Ma Thổi Đèn: Hoàng Bì Tử Phần', '鬼吹灯之龙岭迷窟': 'Ma Thổi Đèn: Long Lĩnh Mê Quật', '鬼吹灯之云南虫谷': 'Ma Thổi Đèn: Côn Trùng Cốc', '鬼吹灯之昆仑神宫': 'Ma Thổi Đèn: Côn Lôn Thần Cung', '鬼吹灯之寻龙决': 'Ma Thổi Đèn: Tầm Long Quyết', '盗墓笔记': 'Đạo Mộ Bút Ký', 'the lost tomb': 'Đạo Mộ Bút Ký', '老九门': 'Lão Cửu Môn', '沙海': 'Sa Hải', '终极笔记': 'Chung Cực Bút Ký', '九层妖塔': 'Cửu Tầng Yêu Tháp', '重启之极海听雷': 'Đạo Mộ Bút Ký: Tái Khởi', '射雕英雄传': 'Anh Hùng Xạ Điêu', 'the legend of the condor heroes': 'Anh Hùng Xạ Điêu', '神雕侠侣': 'Thần Điêu Hiệp Lữ', '倚天屠龙记': 'Ỷ Thiên Đồ Long Ký', '天龙八部': 'Thiên Long Bát Bộ', 'demi-gods and semi-devils': 'Thiên Long Bát Bộ', '笑傲江湖': 'Tiếu Ngạo Giang Hồ', 'the smiling proud wanderer': 'Tiếu Ngạo Giang Hồ', '鹿鼎记': 'Lộc Đỉnh Ký', 'the deer and the cauldron': 'Lộc Đỉnh Ký', '侠客行': 'Hiệp Khách Hành', '雪山飞狐': 'Tuyết Sơn Phi Hồ', '碧血剑': 'Bích Huyết Kiếm', '书剑恩仇录': 'Thư Kiếm Ân Cừu Lục', '连城诀': 'Liên Thành Quyết', '飞狐外传': 'Phi Hồ Ngoại Truyện', '三生三世十里桃花': 'Tam Sinh Tam Thế Thập Lý Đào Hoa', 'eternal love': 'Tam Sinh Tam Thế', '三生三世枕上书': 'Tam Sinh Tam Thế Chẩm Thượng Thư', '花千骨': 'Hoa Thiên Cốt', 'the journey of flower': 'Hoa Thiên Cốt', '甄嬛传': 'Chân Hoàn Truyện', 'empresses in the palace': 'Chân Hoàn Truyện', '琅琊榜': 'Lang Da Bang', 'nirvana in fire': 'Lang Da Bang', '琅琊榜之风起长林': 'Lang Da Bang: Phong Khởi Trường Lâm', '陈情令': 'Trần Tình Lệnh', 'the untamed': 'Trần Tình Lệnh', '长相思': 'Trường Tương Tư', '香蜜沉沉烬如霜': 'Hương Mật Tựa Khói Sương', 'ashes of love': 'Hương Mật Tựa Khói Sương', '庆余年': 'Khánh Dư Niên', 'joy of life': 'Khánh Dư Niên', '雪中悍刀行': 'Tuyết Trung Hãn Đao Hành', '斗破苍穹': 'Đấu Phá Thương Khung', 'battle through the heavens': 'Đấu Phá Thương Khung', '斗罗大陆': 'Đấu La Đại Lục', 'soul land': 'Đấu La Đại Lục', '择天记': 'Trạch Thiên Ký', '将夜': 'Tương Dạ', '诛仙': 'Tru Tiên', '青云志': 'Tru Tiên: Thanh Vân Chí', '仙剑奇侠传': 'Tiên Kiếm Kỳ Hiệp', 'chinese paladin': 'Tiên Kiếm Kỳ Hiệp', '仙剑奇侠传三': 'Tiên Kiếm Kỳ Hiệp 3', '知否知否应是绿肥红瘦': 'Minh Lan Truyện', 'story of minglan': 'Minh Lan Truyện', '宸汐缘': 'Thần Tích Duyên', '九州缥缈录': 'Cửu Châu Phiêu Miểu Lục', '封神演义': 'Phong Thần Diễn Nghĩa', '封神榜': 'Phong Thần Bảng', 'the investiture of the gods': 'Phong Thần Diễn Nghĩa', '步步惊心': 'Bộ Bộ Kinh Tâm', 'scarlet heart': 'Bộ Bộ Kinh Tâm', '宫锁心玉': 'Cung Tỏa Tâm Ngọc', '还珠格格': 'Hoàn Châu Cách Cách', 'my fair princess': 'Hoàn Châu Cách Cách', '情深深雨濛濛': 'Tình Thâm Thâm Vũ Mông Mông', '新白娘子传奇': 'Tân Bạch Nương Tử Truyền Kỳ', '大明宫词': 'Đại Minh Cung Từ', '长安十二时辰': 'Trường An Thập Nhị Thời Thần', 'wind start': 'Trường An Thập Nhị Thời Thần', '风起洛阳': 'Phong Khởi Lạc Dương', '锦心似玉': 'Cẩm Tâm Tựa Ngọc', '一代女皇武则天': 'Nhất Đại Nữ Hoàng Võ Tắc Thiên', '武媚娘传奇': 'Võ Mị Nương Truyền Kỳ', '天盛长歌': 'Thiên Thịnh Trường Ca', '汉武大帝': 'Đại Đế Hán Vũ', '大秦帝国': 'Đại Tần Đế Quốc', '大秦赋': 'Đại Tần Phú', '大明王朝': 'Đại Minh Vương Triều', '锦绣南歌': 'Cẩm Tú Nam Ca', '皓镧传': 'Hạo Lan Truyện', '独孤皇后': 'Độc Cô Hoàng Hậu', '独孤天下': 'Độc Cô Thiên Hạ', '亲爱的热爱的': 'Yêu Em Từ Cái Nhìn Đầu Tiên', '以家人之名': 'Nhân Danh Gia Đình', '三十而已': 'Tuổi Ba Mươi Chưa Phải Là Hết', '都挺好': 'Gia Đình Không Êm Ấm', '我的前半生': 'Nửa Đời Trước Của Tôi', '欢乐颂': 'Tụng Ca Hoan Lạc', '流金岁月': 'Tháng Năm Rực Rỡ', '山海情': 'Sơn Hải Tình', '人世间': 'Nhân Gian Thế Đạo', '狂飙': 'Cuồng Tiêu', '繁花': 'Phồn Hoa', '漫长的季节': 'Mùa Dài Vô Tận', '隐秘的角落': 'Góc Khuất', 'the bad kids': 'Góc Khuất', '白夜追凶': 'Bạch Dạ Truy Hung', '沉默的真相': 'Sự Thật Im Lặng', '无证之罪': 'Vô Chứng Chi Tội', '余罪': 'Dư Tội', '猎罪图鉴': 'Liệt Tội Đồ Giám', '法医秦明': 'Pháp Y Tần Minh', '心理罪': 'Tâm Lý Tội', '西游记': 'Tây Du Ký', 'journey to the west': 'Tây Du Ký', '三国演义': 'Tam Quốc Diễn Nghĩa', 'romance of the three kingdoms': 'Tam Quốc Diễn Nghĩa', '水浒传': 'Thủy Hử Truyện', 'water margin': 'Thủy Hử Truyện', '红楼梦': 'Hồng Lâu Mộng', 'dream of the red chamber': 'Hồng Lâu Mộng', '七侠五义': 'Thất Hiệp Ngũ Nghĩa', '包青天': 'Bao Công', '武林外传': 'Ngoại Truyện Giang Hồ', '哪吒之魔童降世': 'Na Tra: Ma Đồng Giáng Thế', '姜子牙': 'Khương Tử Nha', '大鱼海棠': 'Đại Ngư Hải Đường', '白蛇：缘起': 'Bạch Xà: Duyên Khởi', '雄狮少年': 'Thiếu Niên Sư Tử', '深海': 'Thâm Hải', '태양의 후예': 'Hậu Duệ Mặt Trời', 'descendants of the sun': 'Hậu Duệ Mặt Trời', '별에서 온 그대': 'Vì Sao Đưa Anh Tới', 'you who came from the stars': 'Vì Sao Đưa Anh Tới', 'my love from the star': 'Vì Sao Đưa Anh Tới', '도깨비': 'Yêu Tinh', 'goblin': 'Yêu Tinh', 'guardian: the lonely and great god': 'Yêu Tinh', '사랑의 불시착': 'Hạ Cánh Nơi Anh', 'crash landing on you': 'Hạ Cánh Nơi Anh', '이태원 클라쓰': 'Tầng Lớp Itaewon', 'itaewon class': 'Tầng Lớp Itaewon', '킹덤': 'Kingdom: Vương Triều Xác Sống', 'kingdom (korean)': 'Kingdom: Vương Triều Xác Sống', '오징어 게임': 'Squid Game', 'squid game': 'Squid Game', '이상한 변호사 우영우': 'Nữ Luật Sư Kỳ Lạ Woo Young Woo', 'extraordinary attorney woo': 'Nữ Luật Sư Kỳ Lạ Woo Young Woo', '더 글로리': 'Vinh Quang Trong Thù Hận', 'the glory': 'Vinh Quang Trong Thù Hận', '슬기로운 의사생활': 'Những Bác Sĩ Tài Ba', 'hospital playlist': 'Những Bác Sĩ Tài Ba', '미스터 션샤인': 'Mister Sunshine', 'mr. sunshine': 'Mister Sunshine', '빈센조': 'Vincenzo', 'vincenzo': 'Vincenzo', '부부의 세계': 'Thế Giới Hôn Nhân', 'the world of the married': 'Thế Giới Hôn Nhân', '응답하라 1988': 'Hãy Nhớ Mãi 1988', 'reply 1988': 'Hãy Nhớ Mãi 1988', '나의 아저씨': 'Ahjussi Của Em', 'my mister': 'Ahjussi Của Em', '사이코지만 괜찮아': 'Điên Thì Có Sao', "it's okay to not be okay": 'Điên Thì Có Sao', '스물다섯 스물하나': 'Hai Mươi Lăm Hai Mươi Mốt', 'twenty-five twenty-one': 'Hai Mươi Lăm Hai Mươi Mốt', '지금 우리 학교는': 'Ngôi Trường Xác Sống', 'all of us are dead': 'Ngôi Trường Xác Sống', '무빙': 'Moving (Hàn)', 'moving (korean)': 'Moving', '이두나!': 'Doona!', 'doona!': 'Doona!', 'signal 시그널': 'Signal', 'signal (korean)': 'Signal', '무한도전': 'Vô Hạn Thử Thách', '런닝맨': 'Running Man', 'running man': 'Running Man', '기생충': 'Ký Sinh Trùng', 'parasite': 'Ký Sinh Trùng', '부산행': 'Chuyến Tàu Sinh Tử', 'train to busan': 'Chuyến Tàu Sinh Tử', '반도': 'Bán Đảo', 'peninsula (korean)': 'Bán Đảo', '올드보이': 'Oldboy', 'oldboy': 'Oldboy', '아저씨': 'Người Bảo Vệ', 'the man from nowhere': 'Người Bảo Vệ', '범죄도시': 'Thành Phố Tội Ác', 'the roundup': 'Thành Phố Tội Ác', '신과함께': 'Cùng Với Thần', 'along with the gods': 'Cùng Với Thần', '베테랑': 'Cựu Chiến Binh', 'veteran (korean)': 'Cựu Chiến Binh', 'the avengers': 'Biệt Đội Siêu Anh Hùng', 'avengers: endgame': 'Avengers: Hồi Kết', 'avengers: infinity war': 'Avengers: Cuộc Chiến Vô Cực', 'avengers: age of ultron': 'Avengers: Đế Chế Ultron', 'iron man': 'Người Sắt', 'captain america: the first avenger': 'Đội Trưởng Mỹ: Chiến Sĩ Đầu Tiên', 'captain america: the winter soldier': 'Đội Trưởng Mỹ: Chiến Binh Mùa Đông', 'captain america: civil war': 'Đội Trưởng Mỹ: Nội Chiến', 'thor': 'Thần Sấm', 'thor: ragnarok': 'Thần Sấm: Tận Thế', 'thor: love and thunder': 'Thần Sấm: Tình Yêu và Sấm Sét', 'spider-man: no way home': 'Người Nhện: Không Còn Nhà', 'spider-man: homecoming': 'Người Nhện: Trở Về Nhà', 'spider-man: far from home': 'Người Nhện: Xa Nhà', 'black panther': 'Chiến Binh Báo Đen', 'doctor strange': 'Phù Thủy Tối Thượng', 'doctor strange in the multiverse of madness': 'Phù Thủy Tối Thượng: Đa Vũ Trụ Điên Loạn', 'guardians of the galaxy': 'Vệ Binh Dải Ngân Hà', 'ant-man': 'Người Kiến', 'black widow': 'Góa Phụ Đen', 'eternals': 'Những Người Bất Tử', 'shang-chi and the legend of the ten rings': 'Shang-Chi và Huyền Thoại Thập Nhẫn', 'thor: the dark world': 'Thần Sấm: Thế Giới Bóng Tối', 'the incredible hulk': 'Người Khổng Lồ Xanh', 'captain marvel': 'Chiến Binh Marvel', 'wandavision': 'WandaVision', 'loki': 'Loki', 'hawkeye': 'Hawkeye', 'moon knight': 'Hiệp Sĩ Mặt Trăng', 'she-hulk: attorney at law': 'She-Hulk: Nữ Luật Sư', 'ms. marvel': 'Ms. Marvel', 'what if...?': 'Điều Gì Sẽ Xảy Ra Nếu...?', 'the dark knight': 'Kỵ Sĩ Bóng Đêm', 'the dark knight rises': 'Kỵ Sĩ Bóng Đêm Trỗi Dậy', 'batman begins': 'Người Dơi Xuất Hiện', 'batman v superman: dawn of justice': 'Batman đại chiến Superman', 'man of steel': 'Người Thép', 'wonder woman': 'Wonder Woman', 'aquaman': 'Thủy Vương', 'joker': 'Joker', 'suicide squad': 'Đội Cảm Tử', 'the batman': 'The Batman', 'shazam!': 'Shazam!', 'black adam': 'Black Adam', 'blue beetle': 'Bọ Cánh Cứng Xanh', 'titanic': 'Titanic', 'avatar': 'Avatar', 'avatar: the way of water': 'Avatar: Dòng Chảy Của Nước', 'the lord of the rings: the fellowship of the ring': 'Chúa Tể Nhẫn: Hiệp Hội Nhẫn Thần', 'the lord of the rings: the two towers': 'Chúa Tể Nhẫn: Hai Tòa Tháp', 'the lord of the rings: the return of the king': 'Chúa Tể Nhẫn: Sự Trở Về Của Nhà Vua', 'the hobbit: an unexpected journey': 'Người Hobbit: Hành Trình Bất Ngờ', 'the hobbit: the desolation of smaug': 'Người Hobbit: Đất Hoang Smaug', 'the hobbit: the battle of the five armies': 'Người Hobbit: Trận Chiến Năm Cánh Quân', "harry potter and the sorcerer's stone": 'Harry Potter và Hòn Đá Phù Thủy', "harry potter and the philosopher's stone": 'Harry Potter và Hòn Đá Phù Thủy', 'harry potter and the chamber of secrets': 'Harry Potter và Phòng Chứa Bí Mật', 'harry potter and the prisoner of azkaban': 'Harry Potter và Tên Tù Nhân Azkaban', 'harry potter and the goblet of fire': 'Harry Potter và Chén Lửa', 'harry potter and the order of the phoenix': 'Harry Potter và Hội Phượng Hoàng', 'harry potter and the half-blood prince': 'Harry Potter và Hoàng Tử Lai', 'harry potter and the deathly hallows – part 1': 'Harry Potter và Bảo Bối Tử Thần P1', 'harry potter and the deathly hallows – part 2': 'Harry Potter và Bảo Bối Tử Thần P2', 'fantastic beasts and where to find them': 'Sinh Vật Huyền Bí và Nơi Tìm Ra Chúng', 'pirates of the caribbean: the curse of the black pearl': 'Cướp Biển Vùng Caribê: Lời Nguyền Tàu Ngọc Trai', "pirates of the caribbean: dead man's chest": 'Cướp Biển Vùng Caribê: Rương Tử Thần', 'mission: impossible': 'Nhiệm Vụ Bất Khả Thi', 'mission: impossible – fallout': 'Nhiệm Vụ Bất Khả Thi: Sụp Đổ', 'the fast and the furious': 'Quá Nhanh Quá Nguy Hiểm', 'fast & furious': 'Quá Nhanh Quá Nguy Hiểm', 'john wick': 'John Wick', 'john wick: chapter 4': 'John Wick: Chương 4', 'indiana jones and the raiders of the lost ark': 'Indiana Jones và Chiếc Hòm Thất Lạc', 'transformers': 'Transformers', 'jurassic park': 'Công Viên Kỷ Jura', 'jurassic world': 'Thế Giới Kỷ Jura', 'the hunger games': 'Đấu Trường Sinh Tử', 'the hunger games: catching fire': 'Đấu Trường Sinh Tử: Bốc Lửa', 'the hunger games: mockingjay': 'Đấu Trường Sinh Tử: Húng Nhại', 'inception': 'Kẻ Đánh Cắp Giấc Mơ', 'interstellar': 'Hố Đen Tử Thần', 'the martian': 'Người Về Từ Sao Hỏa', 'gravity': 'Lực Hút Trái Đất', 'the matrix': 'Ma Trận', 'the matrix reloaded': 'Ma Trận Tái Tải', 'the matrix revolutions': 'Ma Trận Cách Mạng', 'terminator 2: judgment day': 'Kẻ Hủy Diệt 2', 'gladiator': 'Võ Sĩ Giác Đấu', 'braveheart': 'Trái Tim Dũng Cảm', 'troy': 'Thành Troy', '300': '300 Chiến Binh', 'the mummy': 'Xác Ướp Ai Cập', 'die hard': 'Đương Đầu Với Thử Thách', 'top gun: maverick': 'Phi Công Siêu Đẳng: Maverick', 'top gun': 'Phi Công Siêu Đẳng', 'the shawshank redemption': 'Nhà Tù Shawshank', 'the godfather': 'Bố Già (Mỹ)', 'the godfather part ii': 'Bố Già Phần 2', 'goodfellas': 'Những Tên Xã Hội Đen', 'scarface': 'Mặt Sẹo', 'the silence of the lambs': 'Sự Im Lặng Của Bầy Cừu', 'seven': 'Se7en', 'fight club': 'Hội Đấm Nhau Bí Mật', 'forrest gump': 'Forrest Gump', "schindler's list": 'Danh Sách Của Schindler', 'saving private ryan': 'Giải Cứu Binh Nhì Ryan', 'the green mile': 'Dặm Xanh', 'a beautiful mind': 'Vẻ Đẹp Tâm Hồn', 'catch me if you can': 'Tóm Tôi Nếu Có Thể', 'the wolf of wall street': 'Sói Già Phố Wall', 'the departed': 'Cú Chốt Cuối', 'shutter island': 'Đảo Kinh Hoàng', 'dune': 'Hành Tinh Cát', 'dune: part two': 'Hành Tinh Cát: Phần Hai', 'oppenheimer': 'Oppenheimer', 'barbie': 'Barbie', 'everything everywhere all at once': 'Mọi Thứ Ở Mọi Nơi Cùng Lúc', 'get out': 'Thoát Ra', 'knives out': 'Cuộc Điều Tra Nhà Thrombey', 'glass onion: a knives out mystery': 'Hành Tây Trong Suốt', 'blade runner 2049': 'Tội Phạm Nhân Bản 2049', 'mad max: fury road': 'Mad Max: Con Đường Tử Thần', 'deadpool': 'Deadpool', 'deadpool & wolverine': 'Deadpool & Wolverine', 'x-men': 'Dị Nhân', 'x-men: days of future past': 'Dị Nhân: Ngày Của Tương Lai', 'logan': 'Logan', 'the revenant': 'Người Về Từ Cõi Chết', 'the dark knight trilogy': 'Bộ Ba Kỵ Sĩ Bóng Đêm', 'star wars: a new hope': 'Chiến Tranh Giữa Các Vì Sao: Hy Vọng Mới', 'star wars: the empire strikes back': 'Chiến Tranh Giữa Các Vì Sao: Đế Chế Phản Công', 'star wars: return of the jedi': 'Chiến Tranh Giữa Các Vì Sao: Jedi Trở Về', 'star wars: the force awakens': 'Chiến Tranh Giữa Các Vì Sao: Thức Tỉnh Của Lực Lượng', 'star wars: the last jedi': 'Chiến Tranh Giữa Các Vì Sao: Jedi Cuối Cùng', 'star wars: the rise of skywalker': 'Chiến Tranh Giữa Các Vì Sao: Skywalker Trỗi Dậy', 'rogue one: a star wars story': 'Rogue One: Câu Chuyện Star Wars', 'the mandalorian': 'The Mandalorian', 'andor': 'Andor', 'game of thrones': 'Trò Chơi Vương Quyền', 'house of the dragon': 'Rồng Lửa', 'breaking bad': 'Tội Ác và Hóa Chất', 'better call saul': 'Gọi Cho Saul', 'the walking dead': 'Xác Sống', 'prison break': 'Vượt Ngục', 'friends': 'Những Người Bạn', 'the big bang theory': 'Vụ Nổ Lớn', 'how i met your mother': 'Hành Trình Tìm Kiếm Tình Yêu', 'two and a half men': 'Hai Người Đàn Ông Rưỡi', 'suits': 'Tố Tụng', 'house of cards': 'Ván Bài Lật Ngửa', 'narcos': 'Trùm Ma Túy', 'peaky blinders': 'Những Tên Cướp Đỉnh Cao', 'ozark': 'Ozark', 'mindhunter': 'Thám Tử Tâm Lý', 'true detective': 'Thám Tử Thực Thụ', 'westworld': 'Thế Giới Viễn Tây', "the handmaid's tale": 'Câu Chuyện Người Hầu', 'black mirror': 'Gương Đen', 'stranger things': 'Stranger Things', 'the crown': 'Vương Miện', 'the witcher': 'Thợ Săn Quái Vật', 'bridgerton': 'Bridgerton', 'emily in paris': 'Emily Ở Paris', 'severance': 'Phân Tầng', 'the bear': 'Tiệm Gấu', 'the last of us': 'Những Người Còn Lại', 'euphoria': 'Euphoria', 'succession': 'Kế Thừa', 'rings of power': 'Những Chiếc Nhẫn Quyền Năng', 'the x-files': 'Hồ Sơ Tuyệt Mật', 'criminal minds': 'Hành Vi Phạm Tội', "grey's anatomy": 'Ca Phẫu Thuật Của Grey', 'house m.d.': 'Bác Sĩ House', 'house': 'Bác Sĩ House', 'lost': 'Mất Tích', 'dexter': 'Dexter', 'sherlock': 'Thám Tử Sherlock', 'doctor who': 'Bác Sĩ Who', 'downton abbey': 'Tu Viện Downton', 'the office': 'Chốn Công Sở', 'rick and morty': 'Rick and Morty', 'the simpsons': 'Gia Đình Simpsons', 'family guy': 'Gia Đình Guy', 'south park': 'South Park', 'futurama': 'Futurama', 'it crowd': 'Hội Nghiện Máy Tính', 'the lion king': 'Vua Sư Tử', 'finding nemo': 'Đi Tìm Nemo', 'finding dory': 'Đi Tìm Dory', 'toy story': 'Câu Chuyện Đồ Chơi', 'toy story 4': 'Câu Chuyện Đồ Chơi 4', 'frozen': 'Nữ Hoàng Băng Giá', 'frozen 2': 'Nữ Hoàng Băng Giá 2', 'up': 'Vút Bay', 'inside out': 'Những Mảnh Ghép Cảm Xúc', 'inside out 2': 'Những Mảnh Ghép Cảm Xúc 2', 'coco': 'Hành Trình Đến Xứ Sở Linh Hồn', 'moana': 'Hành Trình Của Moana', 'moana 2': 'Moana 2', 'encanto': 'Ngôi Nhà Phép Thuật', 'turning red': 'Bỗng Dưng Thành Gấu Trúc', 'soul': 'Linh Hồn', 'ratatouille': 'Chú Chuột Đầu Bếp', 'wall-e': 'WALL-E', 'the incredibles': 'Gia Đình Siêu Nhân', 'the incredibles 2': 'Gia Đình Siêu Nhân 2', 'brave': 'Công Chúa Tóc Đỏ', 'monsters, inc.': 'Công Ty Quái Vật', 'cars': 'Câu Chuyện Xe Hơi', 'shrek': 'Shrek', 'kung fu panda': 'Gấu Trúc Kung Fu', 'kung fu panda 4': 'Gấu Trúc Kung Fu 4', 'how to train your dragon': 'Bí Kíp Luyện Rồng', 'despicable me': 'Kẻ Trộm Mặt Trăng', 'minions': 'Minions', 'the secret life of pets': 'Cuộc Sống Bí Mật Của Thú Cưng', 'sing': 'Đại Nhạc Hội', 'zootopia': 'Xứ Sở Diệu Kỳ', 'tangled': 'Công Chúa Tóc Mây', 'cinderella': 'Lọ Lem', 'beauty and the beast': 'Người Đẹp và Quái Vật', 'aladdin': 'Aladdin', 'the little mermaid': 'Nàng Tiên Cá', 'the jungle book': 'Cậu Bé Rừng Xanh', 'snow white and the seven dwarfs': 'Nàng Bạch Tuyết', 'sleeping beauty': 'Công Chúa Ngủ Trong Rừng', 'mulan': 'Hoa Mộc Lan', 'pocahontas': 'Công Chúa Da Đỏ', 'luca': 'Luca', 'lightyear': 'Lightyear', 'elemental': 'Thế Giới Nguyên Tố', 'wish': 'Điều Ước', 'over the hedge': 'Bên Kia Hàng Rào', 'ice age': 'Kỷ Băng Hà', 'the croods': 'Nhà Croods', 'trolls': 'Những Chú Lùn Tinh Nghịch', 'the boss baby': 'Nhóc Trùm', 'puss in boots': 'Mèo Đi Hia', 'madagascar': 'Madagascar', 'spirited away': 'Vùng Đất Linh Hồn', '鋼の錬金術師': 'Cang Giả Kim Thuật Sư', 'fullmetal alchemist: brotherhood': 'Cang Giả Kim Thuật Sư: Brotherhood', '進撃の巨人': 'Đại Chiến Titan', 'attack on titan': 'Đại Chiến Titan', 'shingeki no kyojin': 'Đại Chiến Titan', '鬼滅の刃': 'Thanh Gươm Diệt Quỷ', 'demon slayer': 'Thanh Gươm Diệt Quỷ', 'kimetsu no yaiba': 'Thanh Gươm Diệt Quỷ', '鬼滅の刃 無限列車編': 'Thanh Gươm Diệt Quỷ: Chuyến Tàu Vô Tận', 'demon slayer: mugen train': 'Thanh Gươm Diệt Quỷ: Chuyến Tàu Vô Tận', '呪術廻戦': 'Chú Thuật Hồi Chiến', 'jujutsu kaisen': 'Chú Thuật Hồi Chiến', '僕のヒーローアカデミア': 'Học Viện Siêu Anh Hùng', 'my hero academia': 'Học Viện Siêu Anh Hùng', 'boku no hero academia': 'Học Viện Siêu Anh Hùng', 'ナルト': 'Naruto', 'naruto shippuden': 'Naruto Shippuden', 'ワンピース': 'Đảo Hải Tặc', 'one piece': 'Đảo Hải Tặc', 'ドラゴンボール': 'Bảy Viên Ngọc Rồng', 'dragon ball z': 'Bảy Viên Ngọc Rồng Z', 'dragon ball super': 'Bảy Viên Ngọc Rồng Super', 'ハンターハンター': 'Hunter x Hunter', 'hunter x hunter': 'Hunter x Hunter', '銀魂': 'Thanh Kiếm Bạc', 'gintama': 'Thanh Kiếm Bạc', '名探偵コナン': 'Thám Tử Conan', 'detective conan': 'Thám Tử Conan', 'case closed': 'Thám Tử Conan', 'ドラえもん': 'Doraemon', 'doraemon': 'Doraemon', 'クレヨンしんちゃん': 'Shin - Cậu Bé Bút Chì', 'crayon shin-chan': 'Shin - Cậu Bé Bút Chì', '千と千尋の神隠し': 'Vùng Đất Linh Hồn', 'となりのトトロ': 'Hàng Xóm Của Tôi Là Totoro', 'my neighbor totoro': 'Hàng Xóm Của Tôi Là Totoro', 'ハウルの動く城': 'Lâu Đài Di Động Của Howl', "howl's moving castle": 'Lâu Đài Di Động Của Howl', 'もののけ姫': 'Công Chúa Mononoke', 'princess mononoke': 'Công Chúa Mononoke', '崖の上のポニョ': 'Ponyo Trên Vách Đá', 'ponyo': 'Ponyo Trên Vách Đá', '天空の城ラピュタ': 'Lâu Đài Trên Không', 'castle in the sky': 'Lâu Đài Trên Không', '風の谷のナウシカ': 'Nausicaä Thung Lũng Gió', '君の名は。': 'Your Name', 'your name': 'Your Name', 'kimi no na wa': 'Your Name', '天気の子': 'Đứa Con Của Thời Tiết', 'weathering with you': 'Đứa Con Của Thời Tiết', 'すずめの戸締まり': 'Suzume', 'suzume no tojimari': 'Suzume', 'デスノート': 'Cuốn Sổ Tử Thần', 'death note': 'Cuốn Sổ Tử Thần', 'コードギアス 反逆のルルーシュ': 'Code Geass: Kẻ Phản Loạn Lelouch', 'code geass': 'Code Geass', 'ソードアートオンライン': 'Đao Kiếm Thần Vực', 'sword art online': 'Đao Kiếm Thần Vực', '七つの大罪': 'Bảy Mối Tội Đầu', 'the seven deadly sins': 'Bảy Mối Tội Đầu', 'nanatsu no taizai': 'Bảy Mối Tội Đầu', '転生したらスライムだった件': 'Tôi Bị Chuyển Sinh Thành Slime', 'that time i got reincarnated as a slime': 'Tôi Bị Chuyển Sinh Thành Slime', '東京喰種': 'Quái Dị Tokyo', 'tokyo ghoul': 'Quái Dị Tokyo', 're:zero': 'Re:Zero', 'overlord': 'Overlord', 'no game no life': 'No Game No Life', '俺だけレベルアップな件': 'Solo Leveling', 'solo leveling': 'Solo Leveling', 'エヴァンゲリオン': 'Neon Genesis Evangelion', 'neon genesis evangelion': 'Neon Genesis Evangelion', 'フルーツバスケット': 'Giỏ Trái Cây', 'fruits basket': 'Giỏ Trái Cây', '僕だけがいない街': 'Erased', 'erased': 'Erased', 'steins;gate': 'Steins;Gate', 'cowboy bebop': 'Cowboy Bebop', 'ghost in the shell': 'Vỏ Bọc Ma', 'akira': 'Akira', 'spirited away (japanese)': 'Vùng Đất Linh Hồn', 'grave of the fireflies': 'Mộ Đom Đóm', 'hotaru no haka': 'Mộ Đom Đóm', 'la casa de papel': 'Phi Vụ Triệu Đô', 'money heist': 'Phi Vụ Triệu Đô', 'dark': 'Dark: Khoảng Tối', '1899': '1899', 'lupin': 'Lupin', 'le bureau des légendes': 'Tình Báo Nội Địa', 'the bureau': 'Tình Báo Nội Địa', 'vikings': 'Huyền Thoại Viking', 'the last kingdom': 'Vương Quốc Cuối Cùng', 'outlander': 'Kẻ Ngoài Cuộc', 'babylon berlin': 'Berlin Tội Ác', 'fauda': 'Fauda', 'les misérables': 'Những Người Khốn Khổ', 'les misérables (series)': 'Những Người Khốn Khổ', 'the grand budapest hotel': 'Khách Sạn Grand Budapest', 'amélie': 'Amélie', 'léon: the professional': 'Leon: Sát Thủ Chuyên Nghiệp', 'the intouchables': 'Hai Người Bạn', 'intouchables': 'Hai Người Bạn', 'life is beautiful': 'Cuộc Sống Tươi Đẹp', 'la vita è bella': 'Cuộc Sống Tươi Đẹp', 'city of god': 'Thành Phố Thiên Chúa', 'cidade de deus': 'Thành Phố Thiên Chúa', 'elite': 'Elite', 'money heist: korea': 'Phi Vụ Triệu Đô: Hàn Quốc', 'squid game season 2': 'Squid Game Season 2', 'who killed sara?': 'Ai Đã Giết Sara?', '¿quién mató a sara?': 'Ai Đã Giết Sara?', 'das boot': 'Chiếc Tàu Ngầm', 'run lola run': 'Lola Chạy', 'lola rennt': 'Lola Chạy', 'the lives of others': 'Cuộc Sống Của Người Khác', 'das leben der anderen': 'Cuộc Sống Của Người Khác', "pan's labyrinth": 'Mê Cung Của Pan', 'el laberinto del fauno': 'Mê Cung Của Pan', 'the platform': 'Cái Hố', 'el hoyo': 'Cái Hố', 'money heist (la casa de papel)': 'Phi Vụ Triệu Đô', 'teach you a lesson': 'Bài Học Đáng Đời', '철권교사': 'Bài Học Đáng Đời', 'iron fist education': 'Bài Học Đáng Đời', 'iron fist teacher': 'Bài Học Đáng Đời', 'school king': 'Bài Học Đáng Đời', 'bài học đáng đời': 'Bài Học Đáng Đời'}
CHAR_GLOSSARY_BY_FILM = {'bài học đáng đời': [{'src': 'Xiao Min', 'vi': 'Gong Min'}, {'src': 'xiao min', 'vi': 'Gong Min'}, {'src': '小闵', 'vi': 'Gong Min'}, {'src': 'Na Hwa Jin', 'vi': 'Na Hwa-jin'}, {'src': 'na hwa jin', 'vi': 'Na Hwa Jin'}, {'src': '罗华珍', 'vi': 'Na Hwa Jin'}, {'src': 'Xiao Ba', 'vi': 'trùm trường'}, {'src': 'xiao ba', 'vi': 'trùm trường'}, {'src': '小霸', 'vi': 'trùm trường'}, {'src': '校霸', 'vi': 'trùm trường'}]}

def _get_char_glossary_for_film(vi_title: str) -> list:
    key = (vi_title or '').strip().lower()
    for (film_key, entries) in CHAR_GLOSSARY_BY_FILM.items():
        if film_key in key or key in film_key:
            return entries
    return []
_GLOBAL_SINO_ROLE = {'Cẩu Thối Tử': 'đám lâu la', 'Hiệu Bá': 'trùm trường', 'Lão Bản': 'ông chủ'}

def _post_fix_sino_pinyin(text: str, film_vi_title: str) -> str:
    if text:
        film_overrides = {}
        if film_vi_title:
            entries = _get_char_glossary_for_film(film_vi_title)
            pinyin_to_sino = {'Xiao Min': 'Tiểu Mẫn', 'Xiao Ba': 'Tiểu Bá'}
            for e in entries:
                src = e.get('src', '')
                vi = e.get('vi', '')
                sino = pinyin_to_sino.get(src)
                if sino and vi:
                    film_overrides[sino] = vi
        for (sino, correct) in film_overrides.items():
            text = re.sub('\\b' + re.escape(sino) + '\\b', correct, text)
        for (sino, role) in _GLOBAL_SINO_ROLE.items():
            if sino in film_overrides:
                pass
            else:
                text = re.sub('\\b' + re.escape(sino) + '\\b', role, text)
    return text


def _find_known_titles(text: str) -> list:

    def _norm(s):
        s = re.sub('[:\\-–—.!?\\"\']', ' ', s.lower())
        return re.sub('\\s+', ' ', s).strip()
    text_lower = text.lower()
    text_norm = _norm(text)
    found = []
    for (src, vi) in FILM_TITLE_VI_DICT.items():
        src_lower = src.lower()
        if src_lower in text_lower or _norm(src_lower) in text_norm:
            found.append((vi, src))
    found.sort(key=lambda x: len(x[1]), reverse=True)
    return found

_GT_UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
_GT_FAILS = [0]          # số lần dịch thất bại (trả nguyên văn) — báo ra log thay vì im lặng


def _google_translate(text: str, sl: str, tl: str) -> str:
    """Google Dịch miễn phí. Endpoint `gtx` hay trả 429 với request từ Python (Google nhận dạng kết nối của thư viện),
    nên lùi về endpoint của extension Chrome (`dict-chrome-ex`, cùng dịch vụ). Lỗi hết → trả nguyên văn + đếm lỗi."""
    import time as _t
    for attempt in range(3):
        try:
            r = requests.get('https://translate.googleapis.com/translate_a/single', params={'client': 'gtx', 'sl': sl, 'tl': tl, 'dt': 't', 'q': text},
                             headers=_GT_UA, timeout=20)
            if r.status_code == 200:
                return ''.join((p[0] for p in r.json()[0] if p[0])).strip()
            r = requests.get('https://clients5.google.com/translate_a/t', params={'client': 'dict-chrome-ex', 'sl': sl, 'tl': tl, 'q': text},
                             headers=_GT_UA, timeout=20)
            if r.status_code == 200:
                res = r.json()
                # sl=auto → [[bản dịch, ngôn ngữ]]; còn lại → [bản dịch]
                out = ''.join((x[0] if isinstance(x, list) else x) for x in res).strip()
                if out:
                    return out
        except Exception:
            pass
        if attempt < 2:
            _t.sleep(1.5)
    _GT_FAILS[0] += 1
    return text

def _translate_via_google_free(segments: list, source_lang: str, log_fn, user_context: str, video_filename: str) -> list:
    if segments:
        blocks = _group_segments(segments)
        log_fn(f"   Gộp {len(segments)} segment -> {len(blocks)} block (~{BLOCK_MAX_DUR:.0f}s/block)")
        sl = source_lang if source_lang and source_lang != 'auto' else 'auto'
        _lookup_text = (user_context or '') + ' ' + (video_filename or '')
        _glossary = []
        _known = _find_known_titles(_lookup_text) if _lookup_text.strip() else []
        vi_t = ''
        if _known:
            (vi_t, _src_t) = _known[0]
            _glossary = _get_char_glossary_for_film(vi_t)
        if _known and _glossary:
            log_fn(f"   → Nhận diện phim '{vi_t}' từ mô tả — áp {len(_glossary)} tên nhân vật vào bản dịch miễn phí.")
        try:
            from .tts_engine import replace_numbers_with_words as _r2w
            _has_r2w = True
        except Exception:
            _has_r2w = False
        log_fn('   Dịch miễn phí (Google): gốc → tiếng Anh → tiếng Việt...')
        _GT_FAILS[0] = 0
        translated_scenes = []
        for (i, block) in enumerate(blocks):
            src = block['text'].strip()
            translated_text = src
            if src:
                try:
                    eng = _google_translate(src, sl, 'en')
                    if eng:
                        translated_text = _google_translate(eng, 'en', 'vi')
                    else:
                        translated_text = _google_translate(src, sl, 'vi')
                except Exception as e:
                    log_fn(f'   [WARN] Lỗi dịch đoạn {i + 1}: {e}. Thử dịch thẳng...')
                    try:
                        translated_text = _google_translate(src, sl, 'vi')
                    except Exception:
                        translated_text = src
            if _glossary and translated_text:
                for e in _glossary:
                    (s, v) = ((e.get('src') or '').strip(), (e.get('vi') or '').strip())
                    if s and v and (s.lower() != v.lower()):
                        translated_text = re.sub(re.escape(s), v, translated_text, flags=re.IGNORECASE)
            if _has_r2w and re.search('\\d', translated_text):
                try:
                    translated_text = _r2w(translated_text)
                except Exception:
                    pass
            sub = translated_text
            translated_scenes.append({'voiceover': translated_text, 'clip_start': float(block['start']), 'clip_end': float(block['end']), 'subtitle': sub, 'block_dur': float(block['end']) - float(block['start']), 'orig_text': src})
        if _GT_FAILS[0]:
            log_fn(f'   [WARN] Google Dịch không phản hồi {_GT_FAILS[0]} lần — một số câu còn nguyên văn gốc, kiểm tra mạng rồi chạy lại.')
        log_fn(f'   Hoàn tất dịch Google: {len(translated_scenes)} đoạn.')
        return translated_scenes
    return []

def _glossary_store_dir() -> str:
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    d = os.path.join(base, 'VA_AutoReview', 'glossary')
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d

def _film_key(title: str, user_context: str) -> str:
    raw = (title or '').strip().lower()
    if not raw and user_context:
        raw = user_context.strip().lower()
    raw = re.sub('\\(.*?\\)', ' ', raw)
    raw = re.sub('(tap|phan|part|ep|episode|t)\\s*\\d+', ' ', raw)
    raw = re.sub('[^0-9a-zÀ-ỹ ]+', ' ', raw)
    raw = re.sub('\\s+', '_', raw.strip())
    return raw[:80] or 'unknown'

def _load_film_glossary(key: str) -> list:
    if key:
        p = os.path.join(_glossary_store_dir(), key + '.json')
        try:
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            g = data.get('glossary', []) if isinstance(data, dict) else []
            return [e for e in g if e.get('src') and e.get('vi')]
        except Exception:
            return []
    else:
        return []

def _save_film_glossary(key: str, glossary: list, title: str):
    if key and glossary:
        p = os.path.join(_glossary_store_dir(), key + '.json')
        try:
            merged = {}
            for e in _load_film_glossary(key) + list(glossary):
                s = (e.get('src') or '').strip()
                v = (e.get('vi') or '').strip()
                if s and v and (s.lower() not in merged):
                    merged[s.lower()] = {'src': s, 'vi': v}
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({'title': title, 'glossary': list(merged.values())}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    else:
        return None

def translate_and_localize_transcript(segments: list, api_key: str = '', source_lang: str = 'auto', log_fn=print, openai_key: str = '', polish_with_gpt: bool = False, troll_tone: bool = False, gemini_key: str = '', cost_acc=None, video_filename: str = '', user_context: str = '', allow_web: bool = False) -> list:
    if log_fn is None:
        log_fn = print
    video_filename = video_filename or ''
    user_context = user_context or ''
    deepseek_key = (api_key or '').strip()
    okey = (openai_key or '').strip()
    from core import web_llm
    _wrap = web_llm.with_web if allow_web else (lambda engs: [(e, k) for (e, k) in engs if k])
    if not _wrap([('deepseek', deepseek_key), ('openai', okey)]):
        log_fn('   Dịch miễn phí qua Google (không tốn Token)...')
        return _translate_via_google_free(segments, source_lang, log_fn, user_context=user_context, video_filename=video_filename)
    if segments:
        blocks = _group_segments(segments)
        log_fn(f"   Gộp {len(segments)} segment → {len(blocks)} block (~{BLOCK_MAX_DUR:.0f}s/block)")
        log_fn('   Phân tích ngữ cảnh phim (nhận diện tên riêng, thuật ngữ, hook)...')
        user_context = (user_context or '').strip()
        ctx_chain = _wrap([('deepseek', deepseek_key), ('openai', okey)])
        film_ctx = {}
        for (ce, ck) in ctx_chain:
            film_ctx = _analyze_film_context(blocks, ck, source_lang, log_fn, engine=ce, extra_title_hint=video_filename, user_context=user_context) or {}
            if film_ctx.get('title') or film_ctx.get('glossary') or film_ctx.get('origin'):
                break
            log_fn(f"   Phân tích ngữ cảnh '{ce}' chưa được, thử engine khác...")
        _name_matches = _find_known_titles(video_filename) if video_filename else []
        if video_filename and (not film_ctx.get('_vi_title')) and _name_matches:
            (_vi, _src) = _name_matches[0]
            film_ctx['title'] = f'{_vi} ({_src})'
            film_ctx['_vi_title'] = _vi
            log_fn(f'   → Nhận diện phim từ TÊN FILE: {_vi}')
            _chars_from_file = _get_char_glossary_for_film(_vi)
            if _chars_from_file:
                existing = {e.get('src', '').lower(): True for e in film_ctx.get('glossary', [])}
                for entry in _chars_from_file:
                    if entry['src'].lower() not in existing:
                        film_ctx.setdefault('glossary', []).insert(0, entry)
                log_fn(f'   → Nạp {len(_chars_from_file)} tên nhân vật cố định từ DB')
        if film_ctx.get('origin'):
            log_fn(f"   → Nước sản xuất: {film_ctx.get('origin')}")
        if film_ctx.get('title'):
            log_fn(f"   → Phim: {film_ctx['title']} | Thể loại: {film_ctx.get('genre', '?')}")
        if film_ctx.get('glossary'):
            log_fn(f"   → {len(film_ctx['glossary'])} thuật ngữ/tên riêng được KHÓA cách dịch")
        _vi_title_ctx = film_ctx.get('title', '') or film_ctx.get('_vi_title', '')
        _hard_chars = _get_char_glossary_for_film(_vi_title_ctx)
        if _hard_chars:
            log_fn(f'   → Đã inject {len(_hard_chars)} tên nhân vật cứng từ DB')
        _all_extra = _hard_chars
        if _all_extra:
            existing = {e.get('src', '').lower(): True for e in film_ctx.get('glossary', [])}
            for entry in _all_extra:
                if entry['src'].lower() not in existing:
                    film_ctx.setdefault('glossary', []).insert(0, entry)
                else:
                    for e in film_ctx.get('glossary', []):
                        if e.get('src', '').lower() == entry['src'].lower():
                            e['vi'] = entry['vi']
        film_ctx['_user_context'] = user_context
        _film_key_id = _film_key(film_ctx.get('title', ''), user_context)
        film_ctx['_film_key'] = _film_key_id
        _persisted = _load_film_glossary(_film_key_id)
        if _persisted:
            existing = {e.get('src', '').lower(): e for e in film_ctx.get('glossary', [])}
            for entry in _persisted:
                s = entry['src'].lower()
                if s in existing:
                    existing[s]['vi'] = entry['vi']
                else:
                    film_ctx.setdefault('glossary', []).insert(0, entry)
            log_fn(f'   → Nạp {len(_persisted)} tên/vai trò đã chốt từ tập trước (giữ nhất quán)')
        pivot_engines = _wrap([('deepseek', deepseek_key), ('openai', okey)])
        loc_engines = list(pivot_engines)
        english_texts = _blocks_to_english(blocks, pivot_engines, source_lang, film_ctx, log_fn)
        translated = _localize_to_vietnamese(blocks, english_texts, loc_engines, source_lang, film_ctx, troll_tone, log_fn)
        polish_engines = _wrap([('openai', okey), ('deepseek', deepseek_key)])
        if polish_engines:
            translated = _polish_blocks_chatgpt(translated, polish_engines, log_fn, troll_tone=troll_tone)
        else:
            log_fn('   [3/3] (Bỏ qua bước chuốt ngữ điệu — chưa có API key nào)')
        _vi_title_for_fix = (film_ctx or {}).get('title', '') or (film_ctx or {}).get('_vi_title', '')
        fixed_count = 0
        for (i, txt) in enumerate(translated):
            new_txt = _post_fix_sino_pinyin(txt, _vi_title_for_fix)
            if new_txt != txt:
                fixed_count += 1
                translated[i] = new_txt
        if fixed_count:
            log_fn(f'   [Safety] Đã chuẩn hóa chức danh/biệt danh ở {fixed_count} block')
        try:
            _save_film_glossary(film_ctx.get('_film_key', ''), film_ctx.get('glossary', []), film_ctx.get('title', ''))
        except Exception:
            pass
        import re as _re
        try:
            from .tts_engine import replace_numbers_with_words as _r2w
            _has_r2w = True
        except Exception:
            _has_r2w = False
        scenes = []
        digits_fixed = 0
        for (i, (block, viet_text)) in enumerate(zip(blocks, translated)):
            text = viet_text.strip() if viet_text else block['text']
            if _has_r2w and _re.search('\\d', text):
                try:
                    text = _r2w(text)
                    digits_fixed += 1
                except Exception:
                    pass
            sub = text
            scenes.append({'voiceover': text, 'clip_start': float(block['start']), 'clip_end': float(block['end']), 'subtitle': sub, 'block_dur': float(block['end']) - float(block['start']), 'orig_text': block['text']})
        hook = (film_ctx.get('hook') or '').strip()
        if hook and scenes:
            if _has_r2w and _re.search('\\d', hook):
                try:
                    hook = _r2w(hook)
                except Exception:
                    pass
            scenes[0]['voiceover'] = hook + ' ' + scenes[0]['voiceover']
            scenes[0]['subtitle'] = scenes[0]['voiceover']
            log_fn('   [Hook] Đã chèn câu mở đầu cuốn hút vào cảnh 1')
        if digits_fixed:
            log_fn(f'   [Safety] Đã chuyển số thành chữ ở {digits_fixed} block dịch (an toàn TTS)')
        log_fn(f'   Hoàn tất dịch: {len(scenes)} block sẵn sàng cho TTS')
        return scenes
    log_fn('   [WARN] Transcript rỗng')
    return []

def _group_segments(segments: list) -> list:
    blocks = []
    cur = None
    for seg in segments:
        text = seg.get('text', '').strip()
        if not text:
            pass
        elif cur is None:
            cur = {'start': seg['start'], 'end': seg['end'], 'text': text}
        else:
            dur = seg['end'] - cur['start']
            combined = cur['text'] + ' ' + text
            if dur <= BLOCK_MAX_DUR and len(combined) <= BLOCK_MAX_CHARS:
                cur['end'] = seg['end']
                cur['text'] = combined
            else:
                blocks.append(cur)
                cur = {'start': seg['start'], 'end': seg['end'], 'text': text}
    if cur:
        blocks.append(cur)
    return _split_oversized_blocks(blocks)
_OVERSIZED_BLOCK_DUR = 25.0
_OVERSIZED_BLOCK_CHARS = 260
_SENTENCE_SPLIT_RE = re.compile('(?<=[。！？!?.;；])\\s*')
_CLAUSE_SPLIT_RE = re.compile('(?<=[，,])\\s*')

def _split_oversized_blocks(blocks: list) -> list:
    out = []
    for b in blocks:
        dur = b['end'] - b['start']
        text = b['text'].strip()
        if dur <= _OVERSIZED_BLOCK_DUR and len(text) <= _OVERSIZED_BLOCK_CHARS:
            out.append(b)
        else:
            parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]
            if len(parts) <= 1:
                step = max(_OVERSIZED_BLOCK_CHARS, 80)
                parts = [text[i:i + step] for i in range(0, len(text), step)] or [text]
            out.extend(_distribute_time(parts, b['start'], b['end']))
    return out

def _distribute_time(parts: list, t_start: float, t_end_total: float) -> list:
    total_chars = sum((len(p) for p in parts)) or 1
    total_dur = t_end_total - t_start
    result = []
    t_cursor = t_start
    for (pi, part) in enumerate(parts):
        part_dur = total_dur * (len(part) / total_chars)
        t_end = t_end_total if pi == len(parts) - 1 else min(t_end_total, t_cursor + part_dur)
        t_end = max(t_cursor + 0.05, t_end)
        sub = [q.strip() for q in _CLAUSE_SPLIT_RE.split(part) if q.strip()]
        if t_end - t_cursor > _OVERSIZED_BLOCK_DUR and len(sub) > 1:
            result.extend(_distribute_time(sub, t_cursor, t_end))
        else:
            result.append({'start': t_cursor, 'end': t_end, 'text': part})
        t_cursor = t_end
    return result

def _analyze_film_context(blocks: list, api_key: str, source_lang: str, log_fn, engine: str, extra_title_hint: str, user_context: str) -> dict:
    if blocks:
        n = len(blocks)
        max_lines = 70
        step = max(1, n // max_lines)
        sample_lines = []
        total_chars = 0
        for i in range(0, n, step):
            t = blocks[i]['text'].strip()
            if t:
                sample_lines.append(t)
                total_chars += len(t)
                if total_chars > 6000:
                    break
        sample = '\n'.join(sample_lines)
        lang_hint = f'ngon ngu goc: {source_lang}' if source_lang != 'auto' else 'tu dong phat hien ngon ngu'
        lookup_text = sample + ('\n' + extra_title_hint if extra_title_hint else '')
        known_matches = _find_known_titles(lookup_text)
        known_hint = ''
        _char_glossary_hint = ''
        if known_matches:
            pairs = '; '.join((f'"{src}" = "{vi}"' for (vi, src) in known_matches[:6]))
            known_hint = f'\nTU DIEN CUNG - UU TIEN TUYET DOI (KHONG duoc thay doi, KHONG phien am lai):\n{pairs}\n'
            log_fn(f"   → Từ điển cứng: {'; '.join((vi for (vi, _) in known_matches[:3]))}")
            _vi_title_first = known_matches[0][0] if known_matches else ''
            _char_entries = _get_char_glossary_for_film(_vi_title_first)
            if _char_entries:
                _char_pairs = '; '.join((f'''"{e['src']}" → "{e['vi']}"''' for e in _char_entries[:8]))
                _char_glossary_hint = f'\nGLOSSARY NHAN VAT CUNG (UU TIEN TUYET DOI — KHONG duoc phien am lai):\n{_char_pairs}\n'
                log_fn(f'   → Glossary nhân vật cứng: {len(_char_entries)} mục')
        user_ctx_hint = ''
        if user_context:
            user_ctx_hint = f'\n*** BOI CANH NGUOI DUNG CUNG CAP — UU TIEN TUYET DOI, TIN TUONG HOAN TOAN ***\n{user_context}\n→ Dung dung ten phim, ten/vai tro nhan vat va xuat xu nhu nguoi dung mo ta. Neu nguoi dung da cho biet day la phim Han/Nhat/Thai... thi origin theo do, DU loi thoai goc la tieng Trung (phim long tieng). Dat ten nhan vat theo dung nguoi dung yeu cau.\n'
        prompt = f"""Ban la chuyen gia phan tich phim & dich thuat ({lang_hint}).\nDuoi day la cac doan thoai LAY MAU tu mot video/phim (theo thu tu thoi gian):\n\n{sample}\n\n{user_ctx_hint}{known_hint}{_char_glossary_hint}Hay phan tich va tra ve JSON THUAN TUY theo schema sau (tat ca gia tri tieng Viet co dau):\n{{\n  "title": "ten phim — DICH NGHIA sang TIENG VIET TU NHIEN hoac giu TEN TIENG ANH/ten goc. TUYET DOI KHONG dung ten phien am Han-Viet (vi du KHONG viet \\"Khanh Du Nien\\" ma viet \\"Niem Vui Cuoc Song\\" / \\"Joy of Life\\"). Neu nguoi dung da cho ten phim thi dung dung ten do. Neu khong nhan ra thi mo ta the loai+boi canh.",\n  "origin": "nuoc san xuat goc cua phim: \\"han\\" (Han Quoc) / \\"trung\\" (Trung Quoc) / \\"nhat\\" (Nhat) / \\"au-my\\" / \\"thai\\" (Thai Lan) / \\"khac\\". QUAN TRONG: nhieu phim Han/Thai/Nhat bi LONG TIENG TRUNG roi dang len Douyin/TikTok — DUNG chi dua vao ngon ngu thoai. Hay dua vao BOI CANH VAN HOA & THE CHE: he thong chinh tri (nghi si Quoc hoi + bau cu Tong thong = Han Quoc; khong co bau cu Tong thong = Trung Quoc), trang phuc, mon an, kieu xung ho, ten dia danh, ten goc nhan vat. Neu khong the xac dinh chac chan → tra ve \\"khac\\".",\n  "genre": "the loai (vi du: do mo phieu luu, kinh di, ngon tinh, hanh dong, hoc duong, tu tien...)",\n  "summary": "2-3 cau tom tat boi canh & noi dung chinh, de nguoi dich nam mach truyen",\n  "glossary": [\n    {{"src": "ten rieng / thuat ngu goc", "vi": "ten tieng Viet dung chuan"}}\n  ],\n  "hook": "MOT cau mo dau CUC CUON (kieu giat tit YouTube review phim), khien nguoi xem phai xem tiep ngay. Khong qua 25 chu, khong dung chu so."\n}}\n\nLUU Y CUC KY QUAN TRONG VE TEN NHAN VAT — TUYET DOI KHONG DUNG HAN-VIET:\n- KHONG BAO GIO phien am Han-Viet ten nhan vat (KHONG 'Tieu Phi', 'Tieu Man', 'Truong Tam', 'Lam Kiet'...). Nghe rat 'Trung Quoc hoa', nguoi xem khong thich.\n- Neu BIET CHAC ten that cua nhan vat (nguoi dung cung cap, hoac nhan ra phim): dung ten goc romanized. Phim Han → ten Han (Na Hwa-jin, Gong Min, Kim Min-jae); Nhat → ten Nhat (Tanaka, Sakura); Thai → ten Thai (Somchai, Ploy); Au-My → ten goc (John, Sara).\n- Neu KHONG BIET ten that (phim long tieng Trung, transcript chi co pinyin nhu 'Xiao Piao', 'Xiao Min', 'Xiao Ba'): TUYET DOI KHONG giu pinyin va KHONG Han-Viet hoa. Thay vao do GAN MOT VAI TRO / BIET DANH THUAN VIET, NGAN GON, DE THUONG, theo dung vai tro nhan vat trong phim (vi du: 'cau hoc tro quay', 'co be lop truong', 'ga dau gau', 'thang ban than', 'co giao', 'ong trum'). Trong glossary ghi: src='Xiao Piao' → vi='cau hoc tro quay' (mot vai tro/biet danh CO DINH). PHAI DUNG NHAT QUAN cung mot biet danh cho cung mot nhan vat trong CA PHIM (va ca cac tap sau).\n- TU CHI VAI TRO / CHUC DANH (KHONG PHAI TEN RIENG): 校霸='trum truong', 班长='lop truong', 老师='thay/co giao', 议员='nghi si', 老板='ong chu'. Dich thanh DANH TU CHUNG thuan Viet, KHONG phien am Han-Viet (KHONG 'Hieu Ba').\n- glossary liet ke: tung nhan vat chinh (src = ten/pinyin trong transcript, vi = ten that romanized HOAC vai tro/biet danh thuan Viet), dia danh, chuc danh hay gap.\n- hook bam sat the loai & boi canh that, khong bia dat.\nChi tra ve JSON, khong them giai thich."""
        try:
            content = _engine_call(engine, api_key, prompt, log_fn, temperature=0.4, max_tokens=3000)
            if content:
                content = re.sub('^```(?:json)?\\s*', '', content)
                content = re.sub('\\s*```$', '', content).strip()
                data = json.loads(_clean_json_newlines(content))
                gloss = []
                for g in data.get('glossary', []) or []:
                    try:
                        s = str(g.get('src', '')).strip()
                        v = str(g.get('vi', '')).strip()
                        if s and v:
                            gloss.append({'src': s, 'vi': v})
                    except Exception:
                        pass
                for (vi_title, src_title) in reversed(known_matches[:5]):
                    gloss.insert(0, {'src': src_title, 'vi': vi_title})
                if known_matches:
                    if not data.get('title') or data.get('title', '?') == '?':
                        (vi_t, src_t) = known_matches[0]
                        data['title'] = f'{vi_t} ({src_t})'
                data['glossary'] = gloss[:45]
                return data
            log_fn('   [WARN] Phân tích ngữ cảnh thất bại — bỏ qua, dịch bình thường')
            if known_matches:
                gloss_fallback = [{'src': src, 'vi': vi} for (vi, src) in known_matches[:5]]
                (vi_t, src_t) = known_matches[0]
                return {'title': f'{vi_t} ({src_t})', 'glossary': gloss_fallback, 'genre': '', 'summary': '', 'hook': ''}
            return {}
        except Exception as ex:
            log_fn(f'   [WARN] Phân tích ngữ cảnh lỗi: {str(ex)[:80]} — bỏ qua, dịch bình thường')
            if known_matches:
                gloss_fallback = [{'src': src, 'vi': vi} for (vi, src) in known_matches[:5]]
                (vi_t, src_t) = known_matches[0]
                return {'title': f'{vi_t} ({src_t})', 'glossary': gloss_fallback, 'genre': '', 'summary': '', 'hook': ''}
            return {}
    else:
        return {}

def _build_ctx_header(film_ctx: dict) -> str:
    if film_ctx:
        parts = ['NGU CANH PHIM (dung de dich nhat quan, dung thuat ngu):']
        _uc = (film_ctx.get('_user_context') or '').strip()
        if _uc:
            parts.append(f'- BOI CANH NGUOI DUNG CUNG CAP (UU TIEN TUYET DOI): {_uc}')
        if film_ctx.get('title'):
            parts.append(f"- Ten/tac pham: {film_ctx['title']}")
        origin_map = {'han': 'Han Quoc', 'trung': 'Trung Quoc/Hoa ngu', 'nhat': 'Nhat Ban', 'au-my': 'Au-My', 'thai': 'Thai Lan'}
        org = (film_ctx.get('origin') or '').strip().lower()
        org_label = origin_map.get(org, org) if org else 'KHONG CHAC CHAN'
        parts.append(f'- Nuoc san xuat: {org_label}')
        if org == 'trung':
            parts.append('  → Phim Trung that su: ten nhan vat phien am Han-Viet pho thong (Truong Tam, Lam Kiet...) — chap nhan duoc. Nhung neu khong chac la phim Trung, dung quy tac vai tro o duoi.')
        elif org == 'han':
            parts.append('  → TEN NHAN VAT dung ten Han romanized (Na Hwa-jin, Gong Min, Kim Min-jae...), TUYET DOI KHONG Han-Viet, DU loi thoai goc la tieng Trung (phim long tieng).')
        elif org == 'nhat':
            parts.append('  → TEN NHAN VAT giu romanization Nhat (Tanaka, Sakura...), KHONG Han-Viet.')
        elif org == 'thai':
            parts.append('  → TEN NHAN VAT giu romanization Thai (Somchai, Ploy, Nong...), KHONG Han-Viet.')
        elif org in ('au-my', 'khac'):
            parts.append('  → TEN NHAN VAT giu ten goc (John, Sara...), KHONG Han-Viet.')
        else:
            parts.append('  → CHUA RO xuat xu → KHONG Han-Viet, KHONG giu pinyin Trung.')
        parts.append('  → UU TIEN GIU TEN NHAN VAT duoc noi trong thoai (dang romanized cua nuoc san xuat). Mot nhan vat goi NHAT QUAN bang MOT ten suot phim, KHONG doi qua doi lai.')
        parts.append('  → CHI khi nhan vat HOAN TOAN khong co ten (khong ai goi ten) thi moi goi theo VAI TRO thuan Viet ngan gon (nguoi me, dua con, ong chu, co giao...), va giu nhat quan. TUYET DOI KHONG Han-Viet hoa ten Han/Nhat/Thai.')
        if film_ctx.get('genre'):
            parts.append(f"- The loai: {film_ctx['genre']}")
        if film_ctx.get('summary'):
            parts.append(f"- Tom tat: {film_ctx['summary']}")
        gloss = film_ctx.get('glossary') or []
        if gloss:
            pairs = '; '.join((f"{g['src']} = {g['vi']}" for g in gloss))
            parts.append(f'- TU DIEN BAT BUOC (luon dich dung nhu sau): {pairs}')
        parts.append('')
        return '\n'.join(parts)
    return ''




def _engine_call(engine: str, key: str, prompt: str, log_fn, temperature: float, max_tokens: int) -> str:
    """AI dịch = tài khoản ChatGPT/Gemini đăng nhập trong app (engine 'web')."""
    from core import web_llm
    return web_llm.chat(prompt, log_fn)

def _parse_id_text(content: str, list_key: str) -> dict:
    if content:
        content = re.sub('^```(?:json)?\\s*', '', content)
        content = re.sub('\\s*```$', '', content).strip()
        content = _clean_json_newlines(content)
        content = _escape_inner_quotes(content)
        mapping = {}
        try:
            data = json.loads(content)
            items = data if isinstance(data, list) else (data.get(list_key, []) if isinstance(data, dict) else [])
            for item in items:
                try:
                    mapping[int(item['id'])] = str(item['text']).strip()
                except Exception:
                    pass
        except Exception:
            for blk in re.findall('\\{[^{}]*\\}', content):
                id_m = re.search('"id"\\s*:\\s*(\\d+)', blk)
                text_m = re.search('"text"\\s*:\\s*"([\\s\\S]*)"', blk)
                if id_m and text_m:
                    val = text_m.group(1)
                    if val.endswith('"'):
                        val = val[:-1]
                    mapping[int(id_m.group(1))] = val.strip().replace('\\n', '\n').replace('\\"', '"')
        return mapping
    return {}

def _try_engines(engines: list, prompt: str, log_fn, temperature: float, max_tokens: int, list_key: str, min_items: int) -> dict:
    best = {}
    remaining = [(e, k) for (e, k) in engines if k]
    for (idx, (eng, k)) in enumerate(remaining):
        content = _engine_call(eng, k, prompt, log_fn, temperature, max_tokens)
        mp = _parse_id_text(content, list_key)
        if len(mp) >= min_items:
            return mp
        if len(mp) > len(best):
            best = mp
        next_engines = [e for (e, _) in remaining[idx + 1:]]
        if next_engines:
            if mp:
                log_fn(f"   [FALLBACK] '{eng}' trả {len(mp)}/{min_items} dòng → chuyển sang '{next_engines[0]}'...")
            else:
                log_fn(f"   [FALLBACK] '{eng}' lỗi / hết quota → chuyển sang '{next_engines[0]}'...")
    return best

def _english_prompt(batch: list, offset: int, lang_hint: str, gloss_hint: str) -> str:
    lines = '\n'.join((f"[{offset + i}] {b['text']}" for (i, b) in enumerate(batch)))
    return f'You are a professional subtitle translator ({lang_hint}).\n{gloss_hint}Translate the following {len(batch)} subtitle lines into clear, accurate ENGLISH. This is an intermediate pass — preserve the meaning faithfully and unambiguously. Keep the SAME number of lines and the SAME IDs. Do not merge or split lines.\n\n{lines}\n\nEscape any double quotes inside text as \\". Return ONLY JSON:\n{{ "translations": [{{"id": {offset}, "text": "english..."}}, ...] }}'

def _blocks_to_english(blocks: list, engines: list, source_lang: str, film_ctx: dict, log_fn) -> list:
    n = len(blocks)
    results = [''] * n
    lang_hint = f'source language: {source_lang}' if source_lang and source_lang != 'auto' else 'auto-detect the source language'
    org = ((film_ctx or {}).get('origin') or '').strip().lower()
    if org == 'trung':
        org_hint = 'This is a CHINESE work. Use standard pinyin / well-known English names for characters. '
    elif org == 'han':
        org_hint = 'This is a KOREAN drama (it may be Chinese-dubbed). Render character names in standard Korean romanization (e.g. Kim Min-jae, Lee Soo-jin, Park) — NEVER Sino-Vietnamese — even if the source audio/subtitles are in Chinese. '
    elif org == 'nhat':
        org_hint = 'This is a JAPANESE work. Keep character names in standard Japanese romanization (e.g. Tanaka, Sakura). '
    elif org == 'thai':
        org_hint = 'This is a THAI work. Keep character names in standard Thai romanization (e.g. Somchai, Ploy, Nong). '
    elif org in ('au-my', 'au_my', 'aumy', 'khac'):
        org_hint = 'Keep original English/Western names exactly as-is. '
    else:
        org_hint = 'Origin uncertain — keep character names in neutral romanized form and do NOT convert them to Sino-Vietnamese readings unless the work is clearly Chinese. '
    title = (film_ctx or {}).get('title') or ''
    title_hint = f'The film/show is: "{title}". ' if title else ''
    role_hint = "Translate role/title words as common nouns, NOT names (e.g. 校霸 = 'the school bully', 班长 = 'class president', 议员 = 'congressman'). "
    gloss = (film_ctx or {}).get('glossary') or []
    gloss_hint = title_hint + org_hint + role_hint
    if gloss:
        pairs = '; '.join((f"{g['src']}" for g in gloss[:40]))
        gloss_hint += f'\nThese are proper nouns / fixed terms — transliterate them, do NOT translate into literal English words: {pairs}\n'
    else:
        gloss_hint += '\n'
    eng_label = engines[0][0] if engines else '?'
    for s in range(0, n, BATCH_BLOCKS):
        e = min(s + BATCH_BLOCKS, n)
        batch = blocks[s:e]
        log_fn(f'   [1/3] Dịch sang tiếng Anh trung gian: block {s + 1}-{e}/{n} ({eng_label})...')
        prompt = _english_prompt(batch, s, lang_hint, gloss_hint)
        mp = _try_engines(engines, prompt, log_fn, 0.2, min(8000, len(batch) * 70 + 500), 'translations', min_items=max(1, len(batch) // 2))
        for (k, v) in mp.items():
            if 0 <= k < n:
                results[k] = v
        if e < n:
            time.sleep(0.8)
    for i in range(n):
        if not results[i]:
            results[i] = blocks[i]['text']
    return results

def _localize_to_vietnamese(blocks: list, english_texts: list, engines: list, source_lang: str, film_ctx: dict, troll_tone: bool, log_fn) -> list:
    n = len(blocks)
    results = [''] * n
    ctx_header = _build_ctx_header(film_ctx)
    tone_str = 'Giong van: hoi troll, vui ve, cham biem di dom de nguoi xem thich thu bat cuoi.\n' if troll_tone else 'Giong van: nghiem tuc, chuan muc, sat voi ngu canh va cam xuc that cua video goc.\n'
    eng_label = engines[0][0] if engines else '?'
    for s in range(0, n, BATCH_BLOCKS):
        e = min(s + BATCH_BLOCKS, n)
        log_fn(f'   [2/3] Địa phương hóa tiếng Việt: block {s + 1}-{e}/{n} ({eng_label})...')
        lines = '\n'.join((f"[{s + i}] GOC: {blocks[s + i]['text']}\n     ENG: {english_texts[s + i]}" for i in range(e - s)))
        prompt = f"""Ban la dich gia chuyen dia phuong hoa phim nuoc ngoai sang tieng Viet.\n{ctx_header}Duoi day la {e - s} doan thoai. Moi doan co BAN GOC (ngon ngu goc) va ban dich TIENG ANH trung gian de ban hieu DUNG nghia. Viet lai sang TIENG VIET tu nhien, muot ma, dung mach truyen.\n\n{lines}\n\nNHIEM VU & QUY TAC:\n- Dich du {e - s} dong, giu nguyen so dong va ID.\n- Phong cach loi an khanh YouTube Viet Nam (kieu Pikachu Review, Sakura Review): tu nhien, dung thanh ngu Viet, cau van luu loat.\n- DICH THOAT Y, KHONG dich tung chu mot: doc HIEU Y NGHIA tong the cua ban tieng Anh trung gian roi VIET LAI bang cau tieng Viet tu nhien nguoi Viet hay noi, KHONG giu cau truc ngu phap tieng Anh (TRANH cau van cung nhac, dao ngu ky la, dich sat nghia den lam toi nghia).\n- DA DANG HOA DAI TU XUNG HO nhan vat: TUYET DOI TRANH lap lai may moc 'anh ta'/'co ta' o gan het cac cau. Tuy ngu canh va sac thai, luan phien dung cac dai tu/cach goi da dang: 'han', 'ga', 'ga ta', 'thang nay', 'y', 'co nang', 'co ay', 'mu ta', 'ten do', 'gã kia'... de van phong sinh dong, khong nhao nhet.\n- LOAI BO LOI DICH MAY NGO NGHE: ban dich phai doc lien mach nhu nguoi ke chuyen thuc su, khong con dau vet dich tung tu, khong dung tu Han Viet cung nhac khi co tu thuan Viet tu nhien hon.\n{tone_str}- BAT BUOC tuan theo TU DIEN + NUOC SAN XUAT trong NGU CANH PHIM o tren: ten rieng/thuat ngu dich y HET nhu vay, KHONG lay nghia den tu ban tieng Anh (vi du giu 'giang ho', KHONG dich 'rivers and lakes').\n- LUAT TEN NHAN VAT (RAT QUAN TRONG): CHI phien am Han Viet (Truong Tam, Lam Kiet...) khi phim XAC DINH la TRUNG QUOC/HOA NGU. Voi phim HAN QUOC / NHAT / THAI / AU-MY, HOAC khi KHONG CHAC CHAN xuat xu → GIU NGUYEN ten romanized goc (Han: Kim Min Jae, Lee Soo Jin; Nhat: Tanaka, Sakura; Thai: Somchai, Ploy; Au-My: John, Anna...), TUYET DOI KHONG phien am Han Viet — DU loi thoai/phu de goc la tieng Trung (vi day co the la phim nuoc ngoai LONG TIENG TRUNG). Ten tieng Anh luon giu nguyen.\n- DAC BIET: Phim Han/Nhat/Thai bi LONG TIENG TRUNG → ten nhan vat trong transcript la dang pinyin Hoa ngu (Xiao Piao, Xiao Min, Xiao Ba, Xiao Liu...). TUYET DOI KHONG chuyen sang am Han Viet (KHONG viet 'Phieu' tu Xiao Piao, KHONG viet 'Minh' tu Xiao Min, KHONG viet 'Ba' tu Xiao Ba). Thay vao do: giu nguyen dang pinyin (Xiao Piao, Xiao Min) HOAC dat biet danh tieng Viet don gian mieu ta nhan vat (vd: 'thang trum', 'thang nho', 'thang ban nho'). Viec dich 'Xiao Piao' thanh 'Phieu' hay 'Xiao Min' thanh 'Minh' la SAI vi lam nguoi xem tuong day la nhan vat Viet Nam.\n- TU CHI VAI TRO KHONG PHAI TEN: vi du 'school bully' / 校霸 = 'trum truong / dai bang lop' (KHONG dich thanh ten 'Hieu Ba'); 'class president' = 'lop truong'; 'the teacher' = 'thay/co giao'. Dich thanh danh tu chung.\n- Tuy hoan canh, tu dat biet danh di dom cho nhan vat dua tren dac diem (vi du 'anh da den', 'anh lac', 'chua te bong toi'). Neu khong hop thi thoi.\n- Giu do dai cau dich xap xi ban goc de voiceover khop timeline (khong qua dai, khong qua ngan).\n- Khong tu y xuong dong. Bat buoc escape dau nhay kep thanh \\" de khong hong JSON.\nDINH DANG TRA VE: chi JSON thuan tuy: {{ "translations": [{{"id": {s}, "text": "tieng Viet..."}}, ...] }}"""
        mp = _try_engines(engines, prompt, log_fn, 0.3, min(8000, (e - s) * 90 + 500), 'translations', min_items=max(1, (e - s) // 2))
        for (k, v) in mp.items():
            if 0 <= k < n:
                results[k] = v
        if e < n:
            time.sleep(0.8)
    for i in range(n):
        if not results[i]:
            results[i] = english_texts[i] or blocks[i]['text']
    return results

def _clean_json_newlines(s: str) -> str:
    result = []
    in_quotes = False
    escape = False
    for c in s:
        if escape:
            result.append(c)
            escape = False
        elif c == '\\':
            result.append(c)
            escape = True
        elif c == '"':
            in_quotes = not in_quotes
            result.append(c)
        elif c == '\n' and in_quotes:
            result.append('\\n')
        else:
            result.append(c)
    return ''.join(result)

def _escape_inner_quotes(json_str: str) -> str:
    result = []
    i = 0
    n = len(json_str)
    in_string = False
    while i < n:
        c = json_str[i]
        if c == '\\' and i + 1 < n:
            result.append(c)
            result.append(json_str[i + 1])
            i += 2
        else:
            if c == '"':
                if in_string:
                    j = i + 1
                    while j < n and json_str[j].isspace():
                        j += 1
                    if j >= n or json_str[j] in ',}]:':
                        in_string = False
                        result.append(c)
                    else:
                        result.append('\\"')
                else:
                    in_string = True
                    result.append(c)
            else:
                result.append(c)
            i += 1
    return ''.join(result)

def _polish_blocks_chatgpt(translated: list, engines: list, log_fn, troll_tone: bool) -> list:
    if engines:
        input_data = [{'id': i, 'text': t} for (i, t) in enumerate(translated)]
        tone_str = 'Giong van: hoi troll, vui ve, cham biem di dom de nguoi xem thich thu bat cuoi.\n' if troll_tone else 'Giong van: nghiem tuc, chuan muc, phu hop ngu canh va bieu cam that cua nhan vat.\n'
        prompt = f"""Ban la bien tap vien chuyen chuot lai loi thuyet minh tieng Viet cho kenh YouTube Viet Nam.\nNhiem vu: Nhan vao danh sach cac doan thoai tieng Viet da dich (co the con lom com, may moc), viet lai moi doan cho tu nhien, luu loat, gong giong thuyet minh phim YouTube Viet Nam (nhu Pikachu Review, Sakura Review). Giu nguyen so doan va ID, khong them khong bot noi dung chinh.\n{tone_str}Quy tac ten rieng & biet danh: GIU NGUYEN cach viet ten nhan vat da co trong ban nhap (KHONG tu y phien am Han Viet lai cac ten dang romanized nhu Kim Min Jae, Tanaka, Somchai, John...). Voi ten phim, dung TEN TIENG VIET PHO BIEN neu da co (vi du: 'Ma Thoi Den', 'Chan Hoan Truyen'). Tu dong dat biet danh di dom cho nhan vat (vi du: 'anh da den', 'anh lac', 'chua te'...) dua tren dac diem.\nYeu cau bo sung (CHAT LUONG DICH): (a) Viet THOAT Y, KHONG may moc — cau van phai doc len tu nhien nhu nguoi Viet ke chuyen, khong con dau vet dich tung chu, khong dao ngu ky la; (b) DA DANG HOA cach xung ho nhan vat — TRANH lap lai may moc 'anh ta'/'co ta', luan phien dung 'han', 'ga', 'ga ta', 'y', 'co nang', 'mu ta', 'ten do'... tuy ngu canh; (c) Loai bo triet de cac cau con lom com/sai ngu phap/nghia mo ho con sot lai tu ban dich may.\nYeu cau: Giu do dai cau polished xap xi va tuong dong voi cau goc de toc do thuyet minh duoc deu dan. Khong viet lai qua dai khien nguoi doc phai doc don dap, tra ve JSON thuan tuy:\n{{"polished": [{{"id": 0, "text": "..."}}, ...]}}\n\nDanh sach ({len(input_data)} doan):\n{json.dumps(input_data, ensure_ascii=False)}"""
        eng_label = engines[0][0] if engines else '?'
        log_fn(f'   [3/3] Chuốt ngữ điệu tiếng Việt ({eng_label})...')
        max_tokens = min(16000, len(translated) * 100 + 500)
        mp = _try_engines(engines, prompt, log_fn, 0.3, max_tokens, 'polished', min_items=max(1, len(translated) // 2))
        if mp:
            return [mp.get(i, t) for (i, t) in enumerate(translated)]
        log_fn('   [WARN] Chuốt ngữ điệu không thành công ở engine nào, giữ bản dịch gốc')
    return translated