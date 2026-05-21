import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildDefaultWorkspaceSourcePayload,
  buildWorkspaceSourcePayload,
  formatWorkspaceSource,
  getAgentWorkspaceBindingPolicy,
  normalizeWorkspaceBindingPolicy
} from '../src/utils/workspaceBindings.js'

test('buildWorkspaceSourcePayload returns null for context-only mode', () => {
  assert.equal(buildWorkspaceSourcePayload({ mode: 'none' }), null)
})

test('buildWorkspaceSourcePayload merges upload bundle ids for upload_bundle mode', () => {
  const payload = buildWorkspaceSourcePayload({
    mode: 'upload_bundle',
    bundleIds: ['bundle-2', 'bundle-1'],
    existingBundleIds: ['bundle-1', 'bundle-3']
  })

  assert.deepEqual(payload, {
    type: 'upload_bundle',
    upload_bundle_ids: ['bundle-1', 'bundle-3', 'bundle-2']
  })
})

test('buildWorkspaceSourcePayload requires an existing path for existing mode', () => {
  assert.throws(
    () => buildWorkspaceSourcePayload({ mode: 'existing', selectedPath: '' }),
    /请选择允许绑定的项目目录/
  )
})

test('formatWorkspaceSource renders name path and flags', () => {
  assert.equal(
    formatWorkspaceSource({
      name: 'project-a',
      path: '/workspace/project-a',
      is_git_repo: true,
      depth: 1
    }),
    'project-a · /workspace/project-a · Git · 深度 1'
  )
})

test('normalizeWorkspaceBindingPolicy maps disabled and existing policies', () => {
  assert.deepEqual(normalizeWorkspaceBindingPolicy({ enabled: false, type: 'existing', path: '/repo' }), {
    enabled: false,
    mode: 'none',
    path: ''
  })
  assert.deepEqual(normalizeWorkspaceBindingPolicy({ type: 'local_path', root: '/repo' }), {
    enabled: true,
    mode: 'existing',
    path: '/repo'
  })
})

test('buildDefaultWorkspaceSourcePayload uses agent config default workspace', () => {
  const agent = {
    config: {
      workspace: {
        default_source: {
          enabled: true,
          type: 'existing',
          path: '/workspace/project'
        }
      }
    }
  }

  assert.deepEqual(getAgentWorkspaceBindingPolicy(agent), {
    enabled: true,
    mode: 'existing',
    path: '/workspace/project'
  })
  assert.deepEqual(buildDefaultWorkspaceSourcePayload({ agent }), {
    type: 'existing',
    path: '/workspace/project'
  })
})
