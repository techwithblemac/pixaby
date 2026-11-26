import socket
import random
import threading
from ..entities.entities import Player

def initialize_server(self, host, port):
    # Create a TCP/IP socket
    self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Bind the socket to the address and port
    self.server_socket.bind((host, port))

    # Listen for incoming connections
    self.server_socket.listen()

    # Initialise
    print(f"Listening on {host} : {port}")

    self.client_list = []


def get_clients(self):
    self.running = True

    while self.running:
        try:
            client, addr = self.server_socket.accept()

            # Create new Player object for the client
            # Spawn player at random coordinates
            x, y = (random.randint(0, 1000), random.randint(-100, 700))

            player = Player(
                800, -900, 50, 50,
                'Torch', 'Yellow',
                game=self, auto=False, client=client
            )
            player.personalise(2)
            
            self.client_list.append(player)
            self.enemy_list.append(player)
            #self.players.append(player)
            self._entities_dirty = True
            
            # Send initial config (ID and entity_id) to the new client
            config_msg = f"$<config>{player.id} {player.entity_id} \n"
            client.send(config_msg.encode('utf-8'))

            print(f"Accepted connection from {addr[0]}:{addr[1]}")

            # Step 1: Notify other players of the new player
            join_msg = (
                f"<join>id={player.id} entity_id={player.entity_id} \n"
            )

            broadcast_to_all_clients(self, join_msg, exclude_player=player)

            # Step 2: Send existing objects to the player

            send_all_objects_to_client(self, player)

            # Step 3: Send info about all existing players to the new client
            for other in [*self.client_list, self.player]:
                if other != player:
                    try:
                        existing_msg = (
                            f"<player>id={other.id} entity_id={other.entity_id} \n"
                        )
                        client.send(existing_msg.encode('utf-8'))
                    except:
                        pass

            # Step 4: Start receiving updates from this client
            client_thread = threading.Thread(target=recv, args=(self, player), daemon=True)
            client_thread.start()

        except Exception as e:
            print("Error accepting client:", e)


def broadcast_to_all_clients(self, message, exclude_player=None):
    for p in self.client_list:
        if p != exclude_player and p.client:
            try:
                p.client.send(message.encode('utf-8'))
            except:
                continue


def recv(self, player):
    buffer = ""
    running_client = True
    while running_client:
        data = player.client.recv(1024).decode('utf-8')

        if not data:
            break  # Client has disconnected

        try:
            # Receive a chunk of data
            buffer += data

            # Handle all complete lines (ending in \n)
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                handle_packet(self, player, line.strip())

        except ConnectionResetError or BrokenPipe:
            print(f"Client {player.entity_id} forcibly disconnected.")
            clean_client(self, player)
            break

        except Exception as e:
            print(f"Error receiving data from {player.entity_id}: {e}")
            break

    clean_client(self, player)


def clean_client(self, player):
    # Cleanup: remove the player and notify others
    print(f"Cleaning up player {player.entity_id}")
    self.client_list.remove(player)
    self.enemy_list.remove(player)
    #self.players.remove(player)
    self._entities_dirty = True

    broadcast_to_all_clients(self, f"<leave>entity_id=player.entity_id", exclude_player=player)

    try:
        player.client.close()
    except:
        pass


def send_sync(self, player, objs):
    #broadcast_object_update(self, player)
    for obj in objs:
        if obj.nature != "entity":
            try:
                if obj.type in ['weapon', 'fire']:
                    message = (
                        f"<update>id={obj.id} object_id={obj.object_id} "
                        f"health={obj.health} type={obj.type} "
                        f"type_size={obj.type_size} type_name={obj.type_name} "
                        f"size={obj.size} sheet_name={obj.sheet_name} "
                        f"name={obj.name} nature={obj.nature} "
                        f"death={obj.death} dead={obj.dead} "
                        f"sprite_index={obj.sprite_index} sprite_sheet={obj.sprite_sheet} "
                        f"rect.x={obj.rect.x} rect.y={obj.rect.y} "
                        f"rect.width={obj.rect.width} rect.height={obj.rect.height} "
                        f"owner.id={obj.owner.id} "
                        f"direction={obj.direction} degree={obj.degree} \n"
                    )
                elif obj.type == "block":
                    message = (
                        f"<update>id={obj.id} object_id={obj.object_id} "
                        f"health={obj.health} type={obj.type} "
                        f"type_size={obj.type_size} type_name={obj.type_name} "
                        f"size={obj.size} "
                        f"name={obj.name} nature={obj.nature} "
                        f"rect.x={obj.rect.x} rect.y={obj.rect.y} "
                        f"rect.width={obj.rect.width} rect.height={obj.rect.height} \n"
                    )

                else:
                    message = (
                        f"<update>id={obj.id} object_id={obj.object_id} "
                        f"health={obj.health} type={obj.type} "
                        f"type_size={obj.type_size} type_name={obj.type_name} "
                        f"size={obj.size} sheet_name={obj.sheet_name} "
                        f"name={obj.name} nature={obj.nature} "
                        f"death={obj.death} dead={obj.dead} "
                        f"sprite_index={obj.sprite_index} sprite_sheet={obj.sprite_sheet} "
                        f"rect.x={obj.rect.x} rect.y={obj.rect.y} "
                        f"rect.width={obj.rect.width} rect.height={obj.rect.height} "
                        f"direction={obj.direction} degree={obj.degree} \n"
                    )

                player.client.send(message.encode('utf-8'))
            except ConnectionResetError or BrokenPipe:
                print(f"Client forcibly disconnected.")
                clean_client(self, player)
                break

            except Exception as e:
                print(f"Failed to send object {obj.object_id}:", e)

        else:
            entity = obj
            try:
                message = (
                    f"<sync>type={entity.type} id={entity.id} "
                    f"entity_id={entity.entity_id} health={entity.health} "
                    f"dead={entity.dead} death={entity.death} "
                    f"name={entity.name} color={entity.color} "
                    f"rect.y={entity.rect.y} rect.x={entity.rect.x} "
                    f"sprite_index={entity.sprite_index} sprite_sheet={entity.sprite_sheet} sheet_name={entity.sheet_name} "
                    f"direction={entity.direction} jump_count={entity.jump_count} "
                    f"x_vel={round(entity.x_vel, 2)} y_vel={round(entity.y_vel, 2)} \n"

                )
                if entity.client:
                    if player == entity.client:
                        message = (
                            f"<sync>type={entity.type} id={entity.id} "
                            f"entity_id={entity.entity_id} health={entity.health} "
                            f"dead={entity.dead} death={entity.death} "
                            f"rect.y={entity.rect.y} rect.x={entity.rect.x} "
                            f"sprite_index={entity.sprite_index} sprite_sheet={entity.sprite_sheet} sheet_name={entity.sheet_name} "
                            f"direction={entity.direction} jump_count={entity.jump_count} "
                            f"x_vel={round(entity.x_vel, 2)} y_vel={round(entity.y_vel, 2)} \n"

                        )
                player.client.send(message.encode('utf-8'))
            except ConnectionResetError or BrokenPipe:
                print(f"Client {player.entity_id} forcibly disconnected.")
                clean_client(self, player)
                break

            except Exception as e:
                print(e, "in server.send_sync()")


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


def handle_packet(self, player, message):
    if message.startswith("<sync>"):
        try:

            # Example:<sync>rect.x=300 rect.y=150 x_vel=2 y_vel=0 health=95 direction=right sprite_index=1
            data = message[7:].split(" ")
            for item in data:
                if "=" in item:
                    key, value = item.split("=")
                    try:
                        parsed_val = parse_value(value)

                        if '.' in key:
                            obj, prop = key.split('.')
                            setattr(getattr(player, obj), prop, parsed_val)
                        else:
                            setattr(player, key, parsed_val)
                        self.b = 'synchronized'
                    except Exception as e:
                        self.b = e
                        # Optional logging
                        continue

        except Exception as e:
            print(f"Error parsing sync packet: {e}")

    elif message.startswith("<chat>"):
        # Chat broadcast (optional)
        try:
            chat_msg = message[6:]
            full_msg = f"<chat>id=player.id {chat_msg}"
            broadcast_to_all_clients(self, full_msg, exclude_player=None)
        except:
            pass

    elif message.startswith("<action>"):
        # Handle game actions (e.g. attack, jump, etc.)
        try:
            action_msg = message[8:]
            data = action_msg.split(" ")
            parsed = dict()

            for item in data:
                if "=" in item:
                    key, value = item.split("=")
                    parsed[key] = value
                    data.remove(item)

            for action in data:
                if 'jump' in action:
                    if player.zone:
                        player.swim_up()
                    elif player.jump_count < 1 or player.jump_count == 1 and player.fall_count > 0.1:
                        player.jump()

                if 'attack' in action:
                    player.attacking = True

                    player.animation_count += 1
                    if "attack" not in player.sprite_sheet:
                        player.animation_count = 0
        except:
            pass


def parse_leave(self, message):
    try:
        player_id = message.split('=')[1]
        #self.players = [p for p in self.players if str(p.id) != player_id]
        self.enemy_list = [p for p in self.enemy_list if str(p.id) != player_id]
        self.client_list = [p for p in self.client_list if str(p.id) != player_id]
    except:
        pass


# ✅ Send All Objects to New Player

def send_all_objects_to_client(self, player):
    for obj in [*self.objects, *[t for t in self.traps if t.name != 'homing'], *self.damageable_objects, *self.treasure_list, *self.fire_list, *self.bombs.list]:
        try:
            if obj.type in ['weapon', 'fire']:
                message = (
                    f"<object>id={obj.id} object_id={obj.object_id} "
                    f"health={obj.health} type={obj.type} "
                    f"type_size={obj.type_size} type_name={obj.type_name} "
                    f"size={obj.size} sheet_name={obj.sheet_name} "
                    f"name={obj.name} nature={obj.nature} "
                    f"death={obj.death} dead={obj.dead} "
                    f"sprite_index={obj.sprite_index} sprite_sheet={obj.sprite_sheet} "
                    f"rect.x={obj.rect.x} rect.y={obj.rect.y} "
                    f"rect.width={obj.rect.width} rect.height={obj.rect.height} "
                    f"owner.id={obj.owner.id} "
                    f"direction={obj.direction} degree={obj.degree} \n"
                )
            else:    
                message = (
                f"<object>id={obj.id} object_id={obj.object_id} type={obj.type} "
                f"type_size={obj.type_size} type_name={obj.type_name} "
                f"size={obj.size} "
                f"name={obj.name} nature={obj.nature} "
                f"dead={obj.dead} death={obj.death} "
                f"rect.x={obj.rect.x} rect.y={obj.rect.y} "
                f"rect.width={obj.rect.width} rect.height={obj.rect.height} \n"
            )
            player.client.send(message.encode('utf-8'))

        except ConnectionResetError or BrokenPipe:
            print(f"Client forcibly disconnected.")
            clean_client(self, player)
            break

        except Exception as e:
            print(f"Failed to send object {obj.object_id}:", e)


# ✅ Broadcast Update to All Players

def broadcast_object_update(self, player):
    for obj in [*self.damageable_objects, *self.treasure_list, *self.fire_list, *self.bombs.list, *self.objects, *[t for t in self.traps if t.name != 'homing']]:
        try:
            
            if obj.type in ['weapon', 'fire']:
                message = (
                    f"<update>id={obj.id} object_id={obj.object_id} "
                    f"health={obj.health} type={obj.type} "
                    f"type_size={obj.type_size} type_name={obj.type_name} "
                    f"size={obj.size} sheet_name={obj.sheet_name} "
                    f"name={obj.name} nature={obj.nature} "
                    f"death={obj.death} dead={obj.dead} "
                    f"sprite_index={obj.sprite_index} sprite_sheet={obj.sprite_sheet} "
                    f"rect.x={obj.rect.x} rect.y={obj.rect.y} "
                    f"rect.width={obj.rect.width} rect.height={obj.rect.height} "
                    f"owner.id={obj.owner.id} "
                    f"direction={obj.direction} degree={obj.degree} \n"
                )
            elif obj.type == "block":
                message = (
                    f"<update>id={obj.id} object_id={obj.object_id} "
                    f"health={obj.health} type={obj.type} "
                    f"type_size={obj.type_size} type_name={obj.type_name} "
                    f"size={obj.size} "
                    f"name={obj.name} nature={obj.nature} "
                    f"rect.x={obj.rect.x} rect.y={obj.rect.y} "
                    f"rect.width={obj.rect.width} rect.height={obj.rect.height} \n"
                )

            else:
                message = (
                    f"<update>id={obj.id} object_id={obj.object_id} "
                    f"health={obj.health} type={obj.type} "
                    f"type_size={obj.type_size} type_name={obj.type_name} "
                    f"size={obj.size} sheet_name={obj.sheet_name} "
                    f"name={obj.name} nature={obj.nature} "
                    f"death={obj.death} dead={obj.dead} "
                    f"sprite_index={obj.sprite_index} sprite_sheet={obj.sprite_sheet} "
                    f"rect.x={obj.rect.x} rect.y={obj.rect.y} "
                    f"rect.width={obj.rect.width} rect.height={obj.rect.height} "
                    f"direction={obj.direction} degree={obj.degree} \n"
                )

            player.client.send(message.encode('utf-8'))
        except ConnectionResetError or BrokenPipe:
            print(f"Client forcibly disconnected.")
            clean_client(self, player)
            break

        except Exception as e:
            print(f"Failed to send object {obj.object_id}:", e)


# ❌ Broadcast Destruction

def broadcast_object_destroy(self, obj):
    message = f"<destroy>object_id={obj.object_id}\n"
    broadcast_to_all_clients(self, message)
