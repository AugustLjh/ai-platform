import test from 'node:test'
import assert from 'node:assert/strict'
import {
  buildAttachmentAccept,
  canModelAcceptAttachments,
  getAttachmentModalities,
  getSupportedInputModalities
} from '../src/utils/modelCapabilities.js'

test('text-only models do not expose attachment entry points', () => {
  const model = {
    provider: 'deepseek',
    config: {
      endpoint_protocol: 'deepseek.chat_completions',
      input_modalities: ['text']
    }
  }

  assert.deepEqual(getSupportedInputModalities(model), ['text'])
  assert.deepEqual(getAttachmentModalities(model), [])
  assert.equal(canModelAcceptAttachments(model), false)
  assert.equal(buildAttachmentAccept(getAttachmentModalities(model)), '')
})

test('vision and file capable models expose the right accept list', () => {
  const model = {
    provider: 'openai',
    config: {
      endpoint_protocol: 'openai.responses',
      input_modalities: ['text', 'image', 'file']
    }
  }

  assert.deepEqual(getSupportedInputModalities(model), ['text', 'image', 'file'])
  assert.deepEqual(getAttachmentModalities(model), ['image', 'file'])
  assert.equal(canModelAcceptAttachments(model), true)
  assert.equal(buildAttachmentAccept(getAttachmentModalities(model)), 'image/*,.png,.jpg,.jpeg,.webp,.gif,.bmp,.avif,.heic,.txt,.text,.log,.md,.markdown,.pdf,.html,.htm,.csv,.tsv,.doc,.docx,.rtf,.ppt,.pptx,.xls,.xlsx,.json,.jsonl,.yaml,.yml,.xml')
})

test('openai responses exposes audio and video attachment support when declared', () => {
  const model = {
    provider: 'openai',
    config: {
      endpoint_protocol: 'openai.responses',
      input_modalities: ['text', 'image', 'audio', 'video', 'file']
    }
  }

  assert.deepEqual(getSupportedInputModalities(model), ['text', 'image', 'audio', 'video', 'file'])
  assert.deepEqual(getAttachmentModalities(model), ['image', 'audio', 'video', 'file'])
  assert.equal(
    buildAttachmentAccept(getAttachmentModalities(model)),
    'image/*,.png,.jpg,.jpeg,.webp,.gif,.bmp,.avif,.heic,audio/*,.mp3,.wav,.m4a,.aac,.flac,.ogg,.opus,video/*,.mp4,.mov,.mkv,.webm,.avi,.m4v,.txt,.text,.log,.md,.markdown,.pdf,.html,.htm,.csv,.tsv,.doc,.docx,.rtf,.ppt,.pptx,.xls,.xlsx,.json,.jsonl,.yaml,.yml,.xml'
  )
})
