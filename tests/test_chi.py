"""
unittest case.
"""

import re
import unittest
from CHI.chi_util import mask_to_redis_regex


class BaseMock:
    def __init__(self, *av, **kw):
        """Конструктор."""
        self.storage = {}

    def get(self, key):
        """Замена метода get."""
        return self.storage.get(key)

    def set(self, key, value, ttl=None):
        """Замена метода set."""
        self.storage[key] = value
    
    def delete(self, key):
        """Замена метода delete."""
        if key in self.storage:
            del self.storage[key]


class RedisMock(BaseMock):
    """Заглушка."""
    def expire(self, key, ttl):
        """Замена метода expire."""

    def keys(self, mask):
        """Замена метода keys."""
        regex = mask_to_redis_regex(mask)
        regex = re.compile(regex)
        x = []
        for k, v in self.storage.items():
            if regex.search(k):
               x.append(k.encode('utf-8'))

        return x



class RedisClusterMock():
    """Мок для RedisCluster."""

    def __init__(self, *av, **kw):
        """Конструктор."""
        self.storage = {}
        self.connection_pool = self
        self.nodes = self
        self.args = None

    def get_connection_by_node(self, node):
        """Замена метода get_connection_by_node."""
        return self

    def items(self):
        """Замена метода items."""
        return ((0, {"server_type": "master"}),
                (0, {"server_type": "slave"}))

    def send_command(self, *args):
        """Замена метода send_command."""
        self.args = args

    def parse_response(self, connection, command):
        """Замена метода parse_response."""
        if command == 'keys':
            mask = mask_to_redis_regex(self.args[1])
            re_mask = re.compile(mask.encode('utf-8'), re.S)
            m=[key for key in self.storage.keys() if re_mask.match(key)]
            return m

        if command == 'eval':
        
            mask = mask_to_redis_regex(self.args[3])
            re_mask = re.compile(mask.encode('utf-8'), re.S)

            count = 0
            for key in list(self.storage.keys()):
                if re_mask.match(key):
                    del self.storage[key]
                    count += 1
            return count
        return None

    def release(self, connection):
        """Закрытие соединения для connection_pool."""

    def expire(self, key, ttl):
        """Замена метода expire."""

    def get(self, key):
        """Замена метода get."""
        return self.storage.get(key.encode('utf-8'))

    def set(self, key, value, ttl=None):
        """Замена метода set."""
        self.storage[key.encode('utf-8')] = value
    
    def delete(self, key):
        """Замена метода delete."""
        key = key.encode('utf-8')
        if key in self.storage:
            del self.storage[key]



class MemcacheMock(BaseMock):
    """Заглушка."""

import pymemcache.client.base
pymemcache.client.base.Client = MemcacheMock

import rediscluster
rediscluster.RedisCluster = RedisClusterMock

import redis
redis.Redis = RedisMock


from CHI import CHI
from CHI.chi_cache_object import CHI_MAX_TIME
from CHI.exception import CHIStrategyOfEraseException, CHIMethodIsNotSupportedException


class AdvancedTestSuite(unittest.TestCase):
    """Advanced test cases."""

    def test_constructor(self):
        """Тест конструктора."""

        chi = CHI('10.10.10.10:80,10.10.10.20:80')

        self.assertEqual(chi.server, [dict(host='10.10.10.10', port=80), dict(host='10.10.10.20', port=80)])

    def test_set(self):
        """Тест set."""
        chi = CHI('10.10.10.10:80')

        reply = chi.set("type:k1:k2", "Хелло Ворлд!")

        self.assertEqual(reply, chi,
                         "set возвращает себя.")

        chi.set("type:k1:k2", "Хелло Ворлд!", compress=True)
        self.assertEqual(chi.get("type:k1:k2"), "Хелло Ворлд!", "Возвращаются данные сжатые gzip-ом.")

        chi.set("type:k1:k2", "Хелло Ворлд!".encode("cp1251"))
        self.assertEqual(chi.get("type:k1:k2"), "Хелло Ворлд!".encode("cp1251"),
                         "Бинарные данные возвращаются бинарными.")

        chi.set("type:k1:k2", {"x": 26})
        self.assertEqual(chi.get("type:k1:k2"), {"x": 26}, "Возвращаются данные сжатые сериализатором.")


    def test_compress_threshold(self):
        """Тест compress_threshold."""
        chi = CHI('10.10.10.10:80')
        
        chi_cache_object = chi.set_object("k", "Я" * int(1024*64/2))
        self.assertFalse(chi_cache_object.is_compressed, "Длина строки меньше compress_threshold")

        chi_cache_object = chi.set_object("k", "Я" * int(1024*64/2+1))
        self.assertTrue(chi_cache_object.is_compressed, "Длина строки больше compress_threshold")

    def test_max_time(self):
        """Тест max_time."""

        chi = CHI('10.10.10.10:80', expires_in=CHI_MAX_TIME)

        chi.set("type:k1:k2", {"x": 26})
        self.assertEqual(chi.get("type:k1:k2"), {"x": 26}, "Возвращаются данные.")

        chi = CHI('10.10.10.10:80', early_expires_in=CHI_MAX_TIME)

        chi.set("type:k1:k2", {"x": 26})
        self.assertEqual(chi.get("type:k1:k2"), {"x": 26}, "Возвращаются данные.")

        chi = CHI('10.10.10.10:80', early_expires_in=1000)

        chi.set("type:k1:k2", {"x": 26})
        self.assertEqual(chi.get("type:k1:k2"), {"x": 26}, "Возвращаются данные.")

    def test_get(self):
        """Тест set."""
        chi = CHI('10.10.10.10:80')

        self.assertEqual(chi.get("type:k1"), None, "Возвращается None, если нет ключа в хранилище.")

        chi.set("type:k1:k2", "Хелло Ворлд!")

        self.assertEqual(chi.get("type:k1:k2"), "Хелло Ворлд!", "Возвращаются данные.")
        self.assertEqual(chi.get("type:k1:k2", builder=lambda: 10), "Хелло Ворлд!",
                         "builder не устанавливает данные, если ключ есть.")
        self.assertEqual(chi.get("type:k1", builder=lambda: 10), 10,
                         "builder устанавливает данные, если ключа нет.")

    def test_remove(self):
        """Тест remove."""
        chi = CHI('10.10.10.10:80')

        chi.set("type:k1", 10)

        self.assertEqual(chi.get("type:k1"), 10, "Ключ есть.")

        self.assertEqual(chi.remove("type:k1"), chi, "remove всегда возвращает себя.")

        self.assertEqual(chi.get("type:k1"), None, "Возвращается None, если нет ключа в хранилище.")

    def test_early_expires(self):
        """Тест удаления ключа по времени."""
        chi = CHI('10.10.10.10:80')

        chi.set("type:k1", 10, ttl=0)

        self.assertEqual(chi.get("type:k1"), None, "Ключа нет.")

    def test_erase(self):
        """Тест erase."""
        with self.assertRaises(CHIStrategyOfEraseException):
            CHI('10.10.10.10:80', driver="redis-cluster", strategy_of_erase="undefined")

        # Игнорируется в остальных драйверах
        CHI('10.10.10.10:80', driver="redis", strategy_of_erase="undefined")
        self.assertTrue(True)


    def test_erase_lua(self):
        """Тест erase стратегии lua."""
        chi = CHI('10.10.10.10:80')

        chi.set("type:x1:k1:x3", 10)
        self.assertEqual(chi.get("type:x1:k1:x3"), 10, "Ключ есть.")

        chi.remove("type:x1:k1:x3")
        self.assertEqual(chi.get("type:x1:k1:x3"), None, "Ключ удалён.")

        chi.set("type:x1:k1:x3", 10)
        chi.set("type:x1:k2:x3", 20)
        chi.set("type:x1:k3:x3", 30)
        chi.set("type:x1:k3:x2", 6)
        chi.set("type:x1:k3:x3:", 7)
        chi.set("type:x1:k3:x3:x7", 8)

        self.assertEqual(chi.keys("type:x1:k*:x3:?**"), [("type:x1:k1:x3"),
                                                     ("type:x1:k2:x3"),
                                                     ("type:x1:k3:x3"),
                                                     ("type:x1:k3:x3:"),
                                                     ("type:x1:k3:x3:x7"),
                                                     ],
                         "Список ключей по маске.")

        self.assertEqual(chi.erase("type:x1:k*:x3:?**"), 5, "Ключи стёрты по маске.")

        self.assertEqual(chi.get("type:x1:k3:x3"), None, "Ключ удалён.")
        self.assertEqual(chi.get("type:x1:k3:x2:"), None, "Ключ удалён.")
        self.assertEqual(chi.get("type:x1:k3:x2:x7"), None, "Ключ удалён.")
        self.assertEqual(chi.get("type:x1:k3:x2"), 6, "Ключ остался.")

    def test_erase_keys(self):
        """Тест erase для стратегии keys."""
        chi = CHI('10.10.10.10:80', strategy_of_erase='keys')

        chi.set("type:x1:k1:x3", 10)
        self.assertEqual(chi.get("type:x1:k1:x3"), 10, "Ключ есть.")

        chi.remove("type:x1:k1:x3")
        self.assertEqual(chi.get("type:x1:k1:x3"), None, "Ключ удалён.")

        chi.set("type:x1:k1:x3", 10)
        chi.set("type:x1:k2:x3", 20)
        chi.set("type:x1:k3:x3", 30)
        chi.set("type:x1:k3:x2", 6)
        chi.set("type:x1:k3:x3:", 7)
        chi.set("type:x1:k3:x3:x7", 8)

        self.assertEqual(chi.keys("type:x1:k*:x3:?**"), [("type:x1:k1:x3"),
                                                     ("type:x1:k2:x3"),
                                                     ("type:x1:k3:x3"),
                                                     ("type:x1:k3:x3:"),
                                                     ("type:x1:k3:x3:x7"),
                                                     ],
                         "Список ключей по маске.")

        self.assertEqual(chi.erase("type:x1:k*:x3:?**"), 5, "Ключи стёрты по маске.")

        self.assertEqual(chi.get("type:x1:k3:x3"), None, "Ключ удалён.")
        self.assertEqual(chi.get("type:x1:k3:x2:"), None, "Ключ удалён.")
        self.assertEqual(chi.get("type:x1:k3:x2:x7"), None, "Ключ удалён.")
        self.assertEqual(chi.get("type:x1:k3:x2"), 6, "Ключ остался.")


    def test_memcache(self):
        """Тест мемкеша."""
        chi = CHI('10.10.10.10:80', driver="memcache")

        chi.set("type:x1:k1:x3", 10)
        self.assertEqual(chi.get("type:x1:k1:x3"), 10, "Ключ есть.")

        chi.remove("type:x1:k1:x3")
        self.assertEqual(chi.get("type:x1:k1:x3"), None, "Ключ удалён.")

        with self.assertRaises(CHIMethodIsNotSupportedException):
            chi.keys("type:x1:k*:x3")

        with self.assertRaises(CHIMethodIsNotSupportedException):
            chi.erase("type:x1:k*:x3")

    def test_redis(self):
        """Тест мемкеша."""
        chi = CHI('10.10.10.10:80', driver="redis")

        chi.set("type:x1:k1:x3", 10)
        self.assertEqual(chi.get("type:x1:k1:x3"), 10, "Ключ есть.")

        chi.remove("type:x1:k1:x3")
        self.assertEqual(chi.get("type:x1:k1:x3"), None, "Ключ удалён.")

        chi.set("type:x1:k1:x3", 10)
        chi.set("type:x1:k2:x3", 20)
        chi.set("type:x1:k3:x3", 30)
        chi.set("type:x1:k3:x2", 6)
        chi.set("type:x1:k3:x3:", 7)
        chi.set("type:x1:k3:x3:x7", 8)

        self.assertEqual(chi.keys("type:x1:k*:x3:?**"), [("type:x1:k1:x3"),
                                                     ("type:x1:k2:x3"),
                                                     ("type:x1:k3:x3"),
                                                     ("type:x1:k3:x3:"),
                                                     ("type:x1:k3:x3:x7"),
                                                     ],
                         "Список ключей по маске.")

        self.assertEqual(chi.erase("type:x1:k*:x3:?**"), 5, "Ключи стёрты по маске.")

        self.assertEqual(chi.get("type:x1:k3:x3"), None, "Ключ удалён.")
        self.assertEqual(chi.get("type:x1:k3:x2:"), None, "Ключ удалён.")
        self.assertEqual(chi.get("type:x1:k3:x2:x7"), None, "Ключ удалён.")
        self.assertEqual(chi.get("type:x1:k3:x2"), 6, "Ключ остался.")



if __name__ == '__main__':
    unittest.main()
