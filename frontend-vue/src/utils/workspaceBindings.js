export const buildWorkspaceSourcePayload = ({
  mode = 'none',
  selectedPath = '',
  bundleIds = [],
  existingBundleIds = []
} = {}) => {
  if (mode === 'upload_bundle') {
    const mergedBundleIds = Array.from(new Set([
      ...((Array.isArray(existingBundleIds) ? existingBundleIds : []).filter(Boolean)),
      ...((Array.isArray(bundleIds) ? bundleIds : []).filter(Boolean))
    ]))
    if (mergedBundleIds.length === 0) {
      throw new Error('选择“使用上传文件创建副本”时，至少需要上传一个文件或文件夹')
    }
    return {
      type: 'upload_bundle',
      upload_bundle_ids: mergedBundleIds
    }
  }

  if (mode === 'existing') {
    const normalizedPath = String(selectedPath || '').trim()
    if (!normalizedPath) {
      throw new Error('请选择允许绑定的项目目录')
    }
    return {
      type: 'existing',
      path: normalizedPath
    }
  }

  return null
}

export const normalizeWorkspaceBindingPolicy = (value = {}) => {
  const policy = value && typeof value === 'object' ? value : {}
  const mode = String(policy.mode || policy.type || 'none').trim().toLowerCase()
  const path = String(policy.path || policy.root || '').trim()
  const enabled = policy.enabled !== false && !['none', 'context_only', 'disabled'].includes(mode)

  if (!enabled) {
    return { enabled: false, mode: 'none', path: '' }
  }

  if (['existing', 'bound', 'local_path'].includes(mode)) {
    return { enabled: true, mode: 'existing', path }
  }

  if (mode === 'upload_bundle') {
    return { enabled: true, mode: 'upload_bundle', path: '' }
  }

  return { enabled: false, mode: 'none', path: '' }
}

export const getAgentWorkspaceBindingPolicy = (agent = {}) => {
  const config = agent?.config && typeof agent.config === 'object' ? agent.config : {}
  const workspace = config.workspace && typeof config.workspace === 'object' ? config.workspace : {}
  return normalizeWorkspaceBindingPolicy(
    workspace.default_source ||
    workspace.defaultSource ||
    workspace.default_binding ||
    workspace.defaultBinding ||
    {}
  )
}

export const buildDefaultWorkspaceSourcePayload = ({
  agent = {},
  bundleIds = [],
  existingBundleIds = []
} = {}) => {
  const policy = getAgentWorkspaceBindingPolicy(agent)
  if (!policy.enabled) {
    return null
  }
  return buildWorkspaceSourcePayload({
    mode: policy.mode,
    selectedPath: policy.path,
    bundleIds,
    existingBundleIds
  })
}

export const formatWorkspaceSource = (source) => {
  const name = String(source?.name || source?.path || '').trim()
  const path = String(source?.path || '').trim()
  const flags = []
  if (source?.is_git_repo) flags.push('Git')
  if (typeof source?.depth === 'number') flags.push(`深度 ${source.depth}`)
  return [name, path && path !== name ? path : '', flags.join(' · ')].filter(Boolean).join(' · ')
}
