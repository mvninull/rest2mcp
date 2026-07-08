import './app.css'
import { mount } from 'svelte'
import App from './App.svelte'
import { installAppAlert } from './app-alert.js'

installAppAlert()

const app = mount(App, {
  target: document.getElementById('app'),
})

export default app
