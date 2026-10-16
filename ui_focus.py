"""Focus follows explicit navigation, never ordinary answers or checkbox edits."""
import json
import streamlit as st


def queue_focus(selector):
    st.session_state['_action_focus']=selector


def render_focus():
    selector=st.session_state.pop('_action_focus',None)
    if not selector:return
    # Selectors contain app-owned hash IDs only. No document HTML is executed.
    encoded=json.dumps(selector).replace('<','\\u003c')
    st.html('''<script>
    requestAnimationFrame(()=>requestAnimationFrame(()=>requestAnimationFrame(()=>{
      const target=document.querySelector('''+encoded+''');
      if(!target)return;
      target.setAttribute('tabindex','-1');
      target.scrollIntoView({block:'start',behavior:'instant'});
      target.focus({preventScroll:true});
    })));
    </script>''',unsafe_allow_javascript=True)
