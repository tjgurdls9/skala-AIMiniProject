import { createApp } from 'vue'
import App from './App.vue'
import { initTheme } from './composables/theme'
import './styles/base.css'

initTheme()
createApp(App).mount('#app')
