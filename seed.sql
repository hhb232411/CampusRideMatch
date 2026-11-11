-- Demo password for all seed users: password123
INSERT INTO users (username, password_hash, display_name, email, phone) VALUES
('alice', 'scrypt:32768:8:1$iOqYFetEXpyzRQps$acb6f5dfaa7c7f78119fa044232270d08ff706a02ed9807ae44750f3a4b774a97995cb2e452f34f46e00d53ee6b5c181ef6f15af106d0c0b5736a75eb26d6e60', 'Alice Chan', 'alice@example.com', '9123 4567'),
('bob', 'scrypt:32768:8:1$iOqYFetEXpyzRQps$acb6f5dfaa7c7f78119fa044232270d08ff706a02ed9807ae44750f3a4b774a97995cb2e452f34f46e00d53ee6b5c181ef6f15af106d0c0b5736a75eb26d6e60', 'Bob Lee', 'bob@example.com', '9234 5678'),
('carol', 'scrypt:32768:8:1$iOqYFetEXpyzRQps$acb6f5dfaa7c7f78119fa044232270d08ff706a02ed9807ae44750f3a4b774a97995cb2e452f34f46e00d53ee6b5c181ef6f15af106d0c0b5736a75eb26d6e60', 'Carol Wong', 'carol@example.com', '9345 6789');

INSERT INTO location_areas (name) VALUES
('Kowloon Tong 九龙塘'),
('Mong Kok 旺角'),
('Tsim Sha Tsui 尖沙咀'),
('Central 中环'),
('Causeway Bay 铜锣湾'),
('Sha Tin 沙田'),
('Tai Po 大埔'),
('Tseung Kwan O 将军澳'),
('Admiralty 金钟'), ('Wan Chai 湾仔'), ('North Point 北角'),
('Quarry Bay 鲗鱼涌'), ('Chai Wan 柴湾'), ('Kennedy Town 坚尼地城'),
('Pok Fu Lam 薄扶林'), ('Braemar Hill 宝马山'), ('Aberdeen 香港仔'), ('Hung Hom 红磡'),
('Jordan 佐敦'), ('Yau Ma Tei 油麻地'), ('Sham Shui Po 深水埗'),
('Mei Foo 美孚'), ('Diamond Hill 钻石山'), ('Wong Tai Sin 黄大仙'),
('Kwun Tong 观塘'), ('Ho Man Tin 何文田'), ('Tsuen Wan 荃湾'),
('Kwai Fong 葵芳'), ('Tai Wai 大围'), ('Fo Tan 火炭'),
('University Station 大学站'), ('Siu Lek Yuen 小沥源'), ('Ma On Shan 马鞍山'), ('Fanling 粉岭'),
('Sheung Shui 上水'), ('Tuen Mun 屯门'), ('Yuen Long 元朗'),
('Tin Shui Wai 天水围'), ('Hang Hau 坑口'), ('Clear Water Bay 清水湾'),
('Tung Chung 东涌'), ('Hong Kong International Airport 香港国际机场');
