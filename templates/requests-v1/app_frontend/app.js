import {createApp,h} from '/assets/vendor/vue.esm-browser.prod.js';
createApp({
  data:()=>({items:[],title:'',error:'',busy:false}),
  async mounted(){await this.load()},
  methods:{
    async request(path,options){const r=await fetch(path,options);if(!r.ok)throw new Error('요청 실패: '+r.status);return r.json()},
    async load(){try{this.items=await this.request('/api/items')}catch(e){this.error=e.message}},
    async add(e){e.preventDefault();this.busy=true;this.error='';try{await this.request('/api/items',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:this.title})});this.title='';await this.load()}catch(e){this.error=e.message}finally{this.busy=false}},
    async toggle(item){this.busy=true;this.error='';try{await this.request('/api/items/'+item.id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:item.status==='open'?'done':'open'})});await this.load()}catch(e){this.error=e.message}finally{this.busy=false}}
  },
  render(){return h('section',[
    h('h1','문의 처리'),h('p','합성 데이터로 확인하는 작은 업무 앱'),
    h('form',{onSubmit:this.add},[h('label',{for:'title'},'문의 제목'),h('input',{id:'title',value:this.title,onInput:e=>this.title=e.target.value,maxlength:200,required:true}),h('button',{disabled:this.busy},'추가')]),
    h('p',{role:'alert'},this.error),h('p',`전체 ${this.items.length} · 미처리 ${this.items.filter(i=>i.status==='open').length}`),
    h('ul',this.items.map(item=>h('li',{key:item.id},[h('span',`${item.title} · ${item.status==='open'?'미처리':'완료'}`),h('button',{onClick:()=>this.toggle(item),disabled:this.busy},item.status==='open'?'완료로 변경':'다시 열기')])))]);}
}).mount('#app');
