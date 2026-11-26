import socket, threading

from ..entities.entities import Player, Enemy
from ..objects.objects import Treasure, Tree, Arrow, Block, Bomb, Deco, Fire, WaterZone, Trap

def connect_to_server(self, ip, port):
    self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.server.connect((ip, port))
    self.running_server = True

    self.enemy_list = []  # All other players
    self.local_id = None

    # Start receiving thread
    threading.Thread(target=listen_to_server, args=(self,), daemon=True).start()


def send_sync(self, player):
    try:
        if self.request_y < 0:
            message = (
                f"<action>jump \n"
            )
            self.server.send(message.encode('utf-8'))

        if self.request_attack:
            message = (
                f"<action>attack \n"
            )
            self.server.send(message.encode('utf-8'))

        message = (
            f"<sync>type={player.type} name={player.name} "
            f"color={player.color} "
            f"x_vel={self.request_x} \n"
        )
        self.server.send(message.encode('utf-8'))

    except Exception as e:
        self.b = e
        print("Error sending sync:", e)


# 📥 3. Receiving Data From Server

def listen_to_server(self):
    buffer = ""

    while True:
        try:
            data = self.server.recv(1024).decode('utf-8')
            if not data:
                continue  # break

            buffer += data
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                handle_packet(self, line.strip())

        except Exception as e:
            # print("Lost connection to server:", e)
            self.running_server = False
            # break


# 🧩 4. `handle_packet()` on Client

def handle_packet(self, message):
    if message.startswith("$<config>"):
        _, ids = message.split("$<config>")
        self.local_id, self.local_entity_id = ids.strip().split(" ")
        self.player.id = int(self.local_id)
        self.player.entity_id = int(self.local_entity_id)
        print("Received ID:", self.local_id)

    elif message.startswith("<sync>"):
        parse_sync(self, message)

    elif message.startswith("<player>"):
        add_remote_player(self, message)

    elif message.startswith("<join>"):
        add_remote_player(self, message)

    elif message.startswith("<leave>"):
        parse_leave(self, message)

    elif message.startswith("<object>"):
        add_object(self, message)

    elif message.startswith("<update>"):
        parse_object_sync(self, message)

    elif message.startswith("<destroy>"):
        remove_object(self, message)


def parse_value(val):
    if isinstance(val, (int, float)):
        return val
    if val.lower() == 'true':
        return True
    if val.lower() == 'false':
        return False
    try:
        if '.' in val:
            return float(val)
        return int(val)
    except:
        return val  # fallback to string


# 🔁 5. Sync Remote Player State

def parse_sync(self, message):
    data = message[7:].strip().split(" ")
    parsed = {}

    for item in data:
        if '=' in item:
            key, value = item.split('=')
            parsed[key] = value

    if 'entity_id' not in parsed:
        return

    target = None

    for enemy in [*self.enemy_list, self.player]:
        if str(enemy.entity_id) == parsed['entity_id']:
            target = enemy
            break

    if not target:
        add_remote_player(self, message.replace('<sync>', '<player>'))
        return

    if str(target.entity_id) == parsed['entity_id']:
        for key, val in parsed.items():
            if key == 'entity_id':
                continue
            try:
                parsed_val = parse_value(val)

                if '.' in key:
                    obj, prop = key.split('.')
                    setattr(getattr(target, obj), prop, parsed_val)
                else:
                    setattr(target, key, parsed_val)

            except Exception:

                # Optional logging
                pass


# 👥 6. Add Remote Player (`<join>` or `$<player>`)

def add_remote_player(self, message):
    try:
        data = message[message.index(">") + 1:].strip().split(" ")
        parsed = {}
        for item in data:
            if '=' in item:
                key, value = item.split('=')
                parsed[key] = value

        if 'entity_id' not in parsed:
            return

        # Avoid duplicates
        for enemy in self.enemy_list:
            if str(enemy.entity_id) == parsed['entity_id']:
                return

        # Create the player object
        new_enemy = Player(0, 0, 50, 50,
                           auto=False,
                           game=self
                           )
        new_enemy.id = int(parsed['id'])
        new_enemy.entity_id = int(parsed.get('entity_id', 100))

        self.enemy_list.append(new_enemy)
        self._entities_dirty = True
    except Exception as e:
        print("Error adding remote player:", e)


# ❌ 7. Handle `<leave>`

def parse_leave(self, message):
    try:
        player_id = message.split('=')[1]
        self.enemy_list = [p for p in self.enemy_list if str(p.entity_id) != player_id]
    except:
        pass


# ✅ `add_object()` on the Client

def add_object(self, message):
    try:
        data = {}
        for item in message[8:].strip().split():
            if '=' in item:
                k, v = item.split('=')
                data[k] = v

        object_id = data['object_id']
        id_ = data['id']

        # Skip if we already have this object
        for obj in self.objects:
            if str(obj.object_id) == object_id and str(obj.id) == id_:
                return

        new_obj = None
        if data['type'] == 'tree' or data['name'] == 'tree':
            new_obj = Tree(
                int(data['rect.x']),
                int(data['rect.y']),
                self
            )
            self.damageable_objects.append(new_obj)

        if data['type'] == 'weapon':
            enemy = None
            for entity in self.enemy_list + [self.player]:
                if int(data['owner.id']) == entity.id:
                    enemy = entity
                    break
            
            if enemy:
                if data['name'] == 'arrow':
                    new_obj = Arrow.spawn(
                        int(data['rect.x']),
                        int(data['rect.y']),
                        owner=enemy,
                        sounds=self.sounds
                    )

                if data['name'] == 'bomb':
                    new_obj = Bomb.spawn(
                        int(data['rect.x']),
                        int(data['rect.y']),
                        owner=enemy,
                        sounds=self.sounds
                    )

                self.bombs.list.append(new_obj)

        if data['type'] == 'fire':
            enemy = None
            for entity in self.enemy_list + [self.player]:
                if int(data['owner.id']) == entity.id:
                    enemy = entity
                    break
            
            if enemy:
                new_obj = Fire.spawn(
                    int(data['rect.x']),
                    int(data['rect.y']),
                    owner=enemy
                )
                self.fire_list.append(new_obj)

        if data['type'] == 'treasure':
            new_obj = Treasure(
                int(data['rect.x']),
                int(data['rect.y']),
                data['name'],
                self
            )
            self.treasure_list.append(new_obj)

        if data['type'] == 'deco':
            new_obj = Deco(
                int(data['rect.x']),
                int(data['rect.y']),
                data['name'],
                self
            )
            self.damageable_objects.append(new_obj)

        if data['type'] == 'trap':
            # the server sends the picture's rect; the trap wants its grid cell
            new_obj = Trap(
                int(data['rect.x']) - (64 - int(data['rect.width'])) // 2,
                int(data['rect.y']) + int(data['rect.height']) - 64,
                data['name'],
                self
            )
            self.traps.append(new_obj)

        if data['type'] == 'block':
            new_obj = Block(
                int(data['rect.x']),
                int(data['rect.y']),
                int(data['size']),
                int(data['size']),
                data['type_name'],
                data['type_size'],
                game=self
            )
            self.objects.append(new_obj)

        if new_obj:
            new_obj.id = int(data['id'])
            new_obj.object_id = int(data['object_id'])

    except Exception as e:
        self.b = f'{e} in creating objects'
        print("Error adding object:", e)
        print(data)


# 🔁 `update_object()` on the Client

def parse_object_sync(self, message):
    data = message[8:].strip().split(" ")
    parsed = {}

    for item in data:
        if '=' in item:
            key, value = item.split('=')
            parsed[key] = value

    if 'object_id' not in parsed:  # or 'id' not in parsed:
        return

    obj = None
    all_objects = [*self.damageable_objects, *self.fire_list, *self.treasure_list, *self.bombs.list, *self.objects, *self.traps]

    for object_ in all_objects:
        if str(object_.object_id) == parsed['object_id'] and str(object_.id) == parsed['id']:
            obj = object_
            break

    if not obj:
        add_object(self, message.replace('<update>', '<object>'))
        return

    if str(obj.object_id) == parsed['object_id'] and str(obj.id) == parsed['id']:
        for key, val in parsed.items():
            if key == 'object_id' or key == 'id':
                continue
            try:
                parsed_val = parse_value(val)

                if '.' in key:
                    obj_attr, prop = key.split('.')
                    setattr(getattr(obj, obj_attr), prop, parsed_val)
                else:
                    setattr(obj, key, parsed_val)
            except Exception as e:
                self.b = f'{e} in updating blocks'
                # Optional logging
                pass


# ❌ `remove_object()` on the Client

def remove_object(self, message):
    try:
        object_id = message.split('=')[1]
        for obj in self.bombs.list:
            if str(obj.object_id) == object_id:
                obj.return_to_pool()
        self.bombs.list = [obj for obj in self.bombs.list if str(obj.object_id) != object_id]
    except:
        pass

