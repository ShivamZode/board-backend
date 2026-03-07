import json
from channels.generic.websocket import AsyncWebsocketConsumer

# ✅ STATE IS NOW NESTED BY ROOM NAME
global_board_state = {}  # Format: { 'room_name': { 'pageId': [elements] } }
global_files_state = {}  # Format: { 'room_name': { 'fileId': file_data } }
global_current_page = {} # Format: { 'room_name': 'pageId' }

class BoardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Grab the dynamic room name from the URL
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'classroom_{self.room_name}'

        # Initialize state for this specific room if it doesn't exist
        if self.room_name not in global_board_state:
            global_board_state[self.room_name] = {}
            global_files_state[self.room_name] = {}
            global_current_page[self.room_name] = 'default'

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        current_page = global_current_page[self.room_name]
        
        # Send existing state for THIS room to late-joiners
        await self.send(text_data=json.dumps({
            'type': 'initial_state',
            'state': global_board_state[self.room_name].get(current_page, []),
            'files': global_files_state[self.room_name], 
            'currentPage': current_page
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)

        # 1. WIPE BOARD
        if data.get('type') == 'wipe_memory':
            global_board_state[self.room_name].clear()
            global_files_state[self.room_name].clear()
            global_current_page[self.room_name] = 'default'
            await self.channel_layer.group_send(self.room_group_name, { 'type': 'wipe_board_message' })
            return

        # 2. RESTORED: PAGE CHANGE LOGIC
        if data.get('type') == 'page_change':
            global_current_page[self.room_name] = data['pageId']
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'page_change_message',
                    'pageId': data['pageId'],
                    'elements': global_board_state[self.room_name].get(data['pageId'], []),
                    'files': global_files_state[self.room_name]
                }
            )
            return

        # 3. RESTORED: PDF UPLOAD LOGIC
        if data.get('type') == 'load_pdf':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'load_pdf_message',
                    'slides': data['slides'],
                    'method': data.get('method', 'spatial')
                }
            )
            return

        # 4. RESTORED: CAMERA SYNC LOGIC (For "Follow Teacher")
        if data.get('type') == 'camera_sync':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'camera_sync_message',
                    'camera': data['camera']
                }
            )
            return

        # 5. INK AND DRAWING LOGIC
        drawing_data = data.get('drawing_data')
        page_id = data.get('pageId', 'default')

        if drawing_data is not None:
            # Save drawing data specifically to THIS room
            global_board_state[self.room_name][page_id] = drawing_data
            
            if 'files' in data and data['files']:
                global_files_state[self.room_name].update(data['files'])

            await self.channel_layer.group_send(
                self.room_group_name,
                { 
                    'type': 'board_message', 
                    'drawing_data': drawing_data, 
                    'files': data.get('files'), 
                    'pageId': page_id,
                    'clientId': data.get('clientId')
                }
            )

    # --- BROADCAST FUNCTIONS ---
    async def load_pdf_message(self, event):
        await self.send(text_data=json.dumps({'type': 'load_pdf', 'slides': event['slides'], 'method': event['method']}))

    async def page_change_message(self, event):
        await self.send(text_data=json.dumps({'type': 'page_change', 'pageId': event['pageId'], 'elements': event['elements'], 'files': event['files']}))

    async def wipe_board_message(self, event):
        await self.send(text_data=json.dumps({'type': 'wipe_board'}))

    async def camera_sync_message(self, event):
        await self.send(text_data=json.dumps({'type': 'camera_sync', 'camera': event['camera']}))

    async def board_message(self, event):
        await self.send(text_data=json.dumps({'drawing_data': event['drawing_data'], 'files': event.get('files'), 'pageId': event['pageId'], 'clientId': event.get('clientId')}))