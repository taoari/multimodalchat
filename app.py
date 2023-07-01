# app.py : Multimodal Chatbot
import gradio as gr
import random
import time
import os
from pprint import pprint
import mimetypes
import langchain
from dotenv import load_dotenv

from utils import parse_message, format_to_message

load_dotenv()  # take environment variables from .env.

# Used for Radio and CheckboxGroup for convert between text and display text
TEXT2DISPLAY = { 
        'ai_chat': 'AI Chat', 'ai_create': 'AI Create',
        'random': 'Random', 'openai': 'OpenAI', 'stabilityai': 'Stability AI',
        'stateless': 'Stateless', 'stateless_prompted': 'Stateless (Prompted)', 'stateful': 'Stateful', 'history': 'On-Screen History',
        'auto': 'Auto', 'yes': 'Yes', 'no': 'No', 'true': 'True', 'false': 'False',
    }

import llms
from llms import HF_ENDPOINTS

llms.parse_endpoints_from_environ()
llms.register_endpoints_to_text2display(TEXT2DISPLAY)

DISPLAY2TEXT = {v:k for k,v in TEXT2DISPLAY.items()}

TITLE = "Multimodal Chat Demo"

DESCRIPTION = """
## AI Chat

Simply enter text and press ENTER in the textbox to interact with the chatbot.

## AI Create

Upload an image and enter an instruction to edit or enter a description 
to generate the first image; continually use instructions to refine the editing until satisfactory. 

**TIPS**: 

1. always "Clear" the chat history if want to start brand new, AI Create depends on chatbot latest previous image output; 
2. "Undo" and re-"Submit" if the generated image is not satisfactory; 
3. adjust "prompt_strength" (in Parameters) for better authenticity (0.0) or better creativity (1.0); 
"""

SETTINGS = {
    'chat_engine': dict(cls='Radio', choices=list(map(TEXT2DISPLAY.get, ['auto', 'random', 'openai', 'stabilityai'] + list(HF_ENDPOINTS.keys()))), value=TEXT2DISPLAY['auto'], 
            interactive=True, label="Chat engine"),
    'chat_state': dict(cls='Radio', choices=list(map(TEXT2DISPLAY.get, ['stateless', 'stateless_prompted', 'history'])), value=TEXT2DISPLAY['history'], 
            interactive=True, label="Chat state"),
}

PARAMETERS = {
    'temperature': dict(cls='Slider', minimum=0, maximum=1, value=0.7, step=0.1, interactive=True, label="Temperature"),
    'max_new_tokens': dict(cls='Slider', minimum=0, maximum=1024, value=512, step=64, interactive=True, label="Max new tokens"),
    # 'top_k': dict(cls='Slider', minimum=1, maximum=5, value=3, step=1, interactive=True, label="Top K"),
    # 'top_p': dict(cls='Slider', minimum=0, maximum=1, value=0.9, step=0.1, interactive=True, label="Top p"),
    'separater': dict(cls='Markdown', value="Image generation parameters:"),
    'translate': dict(cls='Checkbox', interactive=True, label="Translate", info="Translate into English may generate better results"),
    # 'translate': dict(cls='Radio', choices=list(map(TEXT2DISPLAY.get, ['auto', 'yes', 'no'])), value=TEXT2DISPLAY['auto'], 
    #         interactive=True, label="Translate to english or not"),
    'prompt_strength': dict(cls='Slider', minimum=0, maximum=1, value=0.6, step=0.05, interactive=True, label="Prompt strength"),
}

ATTACHMENTS = {
    'image': dict(cls='Image', type="filepath"),
    'webcam': dict(cls='Image', type="filepath", source="webcam"),
    'audio': dict(cls='Audio', type="filepath"),
    'microphone': dict(cls="Audio", type="filepath", source="microphone"),
    'video': dict(cls="Video"),
    "file": dict(cls="File", type="file"),
    # 'model3d': dict(cls="Model3D"),
}

######################################

CONFIG = {
    'upload_button': True,
}

if CONFIG['upload_button']:
    ATTACHMENTS = {}

def user(history, msg, *attachments):
    _attachments = {name: filepath for name, filepath in zip(ATTACHMENTS.keys(), attachments)}
    print(_attachments)
    msg_dict = dict(text=msg, images=[], audios=[], videos=[], files=[])
    for name, filepath in _attachments.items():
        if filepath is not None:
            if name in ['image', 'webcam']:
                msg_dict['images'].append(filepath)
            elif name in ['audio', 'microphone']:
                msg_dict['audios'].append(filepath)
            elif name in ['video']:
                msg_dict['videos'].append(filepath)
            else:
                msg_dict['files'].append(filepath)
    return history + [[format_to_message(msg_dict), None]], gr.update(value="", interactive=False), \
        *([gr.update(value=None, interactive=False)] * len(attachments))

def user_post():
    if len(ATTACHMENTS) == 0:
        return gr.update(interactive=True)
    else:
        return gr.update(interactive=True), *([gr.update(interactive=True)] * len(ATTACHMENTS))

def user_upload_file(msg, filepath):
    # history = history + [((file.name,), None)]
    mtype = mimetypes.guess_type(filepath.name)[0]
    if mtype.startswith('image'):
        msg += f'<img src="\\file={filepath.name}" alt="{os.path.basename(filepath.name)}"/>'
    elif mtype.startswith('audio'):
        msg += f'<audio controls><source src="\\file={filepath.name}">{os.path.basename(filepath.name)}</audio>'
    elif mtype.startswith('video'):
        msg += f'<video controls><source src="\\file={filepath.name}">{os.path.basename(filepath.name)}</video>'
    else:
        msg += f'<a href="\\file={filepath.name}">📁 {os.path.basename(filepath.name)}</a>'
    return msg

def bot(history, instructions, chat_mode, *args):
    try:
        _settings = {name: value for name, value in zip(SETTINGS.keys(), args[:len(SETTINGS)])}
        _parameters = {name: value for name, value in zip(PARAMETERS.keys(), args[len(SETTINGS):])}

        # convert gr.Radio and gr.CheckboxGroup from display back to text
        _chat_mode = DISPLAY2TEXT[chat_mode]
        _settings['chat_engine'] = DISPLAY2TEXT[_settings['chat_engine']]
        _settings['chat_state'] = DISPLAY2TEXT[_settings['chat_state']]

        # Auto select chat engine according chat mode if it is "auto"
        if _settings['chat_engine'] == 'auto':
            _settings['chat_engine'] = {'ai_chat': 'openai', 'ai_create': 'stabilityai'}.get(_chat_mode)
        
        user_message = history[-1][0]
        chat_engine, chat_state = _settings['chat_engine'], _settings['chat_state']

        bot_message = None
        if chat_engine == 'random':
            # Example multimodal messages
            bot_message = random.choice([
                format_to_message(dict(text="I love cat", images=["https://upload.wikimedia.org/wikipedia/commons/2/25/Siam_lilacpoint.jpg"])),
                format_to_message(dict(text="I hate cat", images=["https://upload.wikimedia.org/wikipedia/commons/thumb/b/b6/Felis_catus-cat_on_snow.jpg/2560px-Felis_catus-cat_on_snow.jpg"])),
                format_to_message(dict(audios=["https://upload.wikimedia.org/wikipedia/commons/2/28/Caldhu.wav"])),
                format_to_message(dict(videos=["https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_1MB.mp4"])),
                format_to_message(dict(files=["https://www.africau.edu/images/default/sample.pdf"])),
            ])
        elif chat_engine in ['openai'] or chat_engine in HF_ENDPOINTS:
            bot_message = llms.bot(history, chat_engine, chat_state, _parameters)
        elif chat_engine == 'stabilityai':
            from langchain.chat_models import ChatOpenAI
            llm = ChatOpenAI(
                model_name="gpt-3.5-turbo",
                temperature=_parameters['temperature'],
                stop=['\nHuman:', '<|endoftext|>'],
                verbose=True,
            )
            import stability_ai
            refine = chat_state in ['stateful', 'history']
            bot_message = stability_ai.bot(user_message, history, 
                refine=refine, prompt_strength=_parameters['prompt_strength'],
                translate=_parameters['translate'], llm=llm)
    except Exception as e:
        bot_message = 'ERROR: ' + str(e)

    if bot_message is None:
        bot_message = f'Unsupported **{TEXT2DISPLAY[chat_engine]}** chat engine in **{TEXT2DISPLAY[chat_state]}** state, \
            please change them in `Settings` and retry!'
    
    # # streaming
    # history[-1][1] = ""
    # for character in bot_message:
    #     history[-1][1] += character
    #     time.sleep(0.05)
    #     yield history

    if isinstance(bot_message, str):
        history[-1][1] = bot_message
    else:
        history[-1][1] = bot_message[0]
        history.extend([(None, msg) for msg in bot_message[1:]])

    print(chat_mode); print(_settings); print(_parameters)
    pprint(history)
    return history

def bot_undo(history, user_message):
    if len(history) >= 1:
        user_message = history[-1][0]
        return history[:-1], user_message
    return history, user_message

def clear_chat():
    # conversation_chain.memory.clear()
    return [], "", *([None] * len(ATTACHMENTS))

def get_demo():

    def _create_from_dict(PARAMS):
        params = {}
        for name, kwargs in PARAMS.items():
            cls_ = kwargs['cls']; del kwargs['cls']
            params[name] = getattr(gr, cls_)(**kwargs)
        return params
    
    # use css and elem_id to format
    css="""#chatbot {
min-height: 600px;
}"""

    with gr.Blocks(css=css) as demo:
        gr.HTML(f"<center><h1>{TITLE}</h1></center>")
        with gr.Accordion("Expand to see Introduction and Usage", open=False):
            gr.Markdown(f"{DESCRIPTION}")
        with gr.Row():
            with gr.Column(scale=1):
                attachments = _create_from_dict(ATTACHMENTS)

                with gr.Accordion("Chat mode", open=True) as chat_mode_accordin:
                    chat_mode = gr.Radio(list(map(TEXT2DISPLAY.get, ['ai_chat', 'ai_create'])), value=TEXT2DISPLAY['ai_chat'], show_label=False, 
                        info="")

                with gr.Accordion("Settings", open=False) as settings_accordin:
                    settings = _create_from_dict(SETTINGS)
                with gr.Accordion("Parameters", open=False) as parameters_accordin:
                    parameters = _create_from_dict(PARAMETERS)

                # with gr.Accordion("Instructions", open=False) as instructions_accordin:
                #     instructions = gr.Textbox(
                #         placeholder="LLM instructions",
                #         value=DEFAULT_INSTRUCTIONS,
                #         show_label=False,
                #         interactive=True,
                #         container=False,
                #     )
                instructions = gr.State()

            with gr.Column(scale=9):
                chatbot = gr.Chatbot(elem_id='chatbot')
                with gr.Row():
                    if CONFIG['upload_button']:
                        with gr.Column(scale=0.5, min_width=30):
                            upload = gr.UploadButton("📁", file_types=["image", "video", "audio", "file"])
                    with gr.Column(scale=8):
                        msg = gr.Textbox(show_label=False,
                            placeholder="Enter text and press ENTER", container=False)
                    with gr.Column(scale=1, min_width=60):
                        submit = gr.Button(value="Submit")
                    with gr.Column(scale=1, min_width=60):
                        undo = gr.Button(value="Undo")
                    with gr.Column(scale=1, min_width=60):
                        # clear = gr.ClearButton([msg, chatbot])
                        clear = gr.Button("Clear") # also clear chatbot memory

        if CONFIG['upload_button']:
            upload.upload(user_upload_file, [msg, upload], [msg], queue=False)
        msg.submit(user, [chatbot, msg] + list(attachments.values()), [chatbot, msg] + list(attachments.values()), queue=False).then(
            bot, [chatbot, instructions, chat_mode] + list(settings.values()) + list(parameters.values()), chatbot
        ).then(
            user_post, None, [msg] + list(attachments.values()), queue=False)
        submit.click(user, [chatbot, msg] + list(attachments.values()), [chatbot, msg] + list(attachments.values()), queue=False).then(
            bot, [chatbot, instructions, chat_mode] + list(settings.values()) + list(parameters.values()), chatbot
        ).then(
            user_post, None, [msg] + list(attachments.values()), queue=False)
        undo.click(bot_undo, [chatbot, msg], [chatbot, msg])
        clear.click(clear_chat, [], [chatbot, msg] + list(attachments.values()))

        with gr.Accordion("Examples", open=False) as examples_accordin:
            chat_examples = gr.Examples(
                [["What's the Everett interpretation of quantum mechanics?", TEXT2DISPLAY['ai_chat']],
                 ['Give me a list of the top 10 dive sites you would recommend around the world.', TEXT2DISPLAY['ai_chat']],
                 ['Write a Python code to calculate Fibonacci numbers.', TEXT2DISPLAY['ai_chat']],
                ],
                inputs=[msg, chat_mode], label="AI Chat Examples",
            )
            create_examples = gr.Examples(
                [['rocket ship launching from forest with flower garden under a blue sky, masterful, ghibli', TEXT2DISPLAY['ai_create']],
                 ['crayon drawing of rocket ship launching from forest', TEXT2DISPLAY['ai_create']],
                ],
                inputs=[msg, chat_mode], label="AI Create Examples",
            )
    return demo

def parse_args():
    """Parse input arguments."""
    import argparse
    parser = argparse.ArgumentParser(
        description='Multimodal Chatbot',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-p', '--port', default=7860, type=int,
        help='port number.')
    parser.add_argument(
        '--debug', action='store_true', 
        help='debug mode.')

    args = parser.parse_args()
    return args


if __name__ == '__main__':

    args = parse_args()
    # WARNING: gobal variables are shared accross users, and should be avoided.

    demo = get_demo()
    demo.queue().launch(share=True, server_port=args.port)