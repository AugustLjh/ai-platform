import { computed, ref } from 'vue'
import { uploadAPI } from '@/api'

const extractApiError = (error, fallback) => (
  error?.response?.data?.detail ||
  error?.response?.data?.error ||
  error?.message ||
  fallback
)

const buildRelativePaths = (files) => files.map((file) => file.webkitRelativePath || file.name)

export function useUploadBundles() {
  const bundles = ref([])
  const uploading = ref(false)
  const uploadError = ref('')
  const fileInputRef = ref(null)
  const folderInputRef = ref(null)

  const bundleIds = computed(() => bundles.value.map((bundle) => bundle.bundle_id).filter(Boolean))
  const totalFiles = computed(() => bundles.value.reduce((sum, bundle) => sum + Number(bundle?.summary?.file_count || 0), 0))

  const uploadedFiles = computed(() => bundles.value.flatMap((bundle) => {
    const files = Array.isArray(bundle?.files) ? bundle.files : []
    return files.map((file) => ({
      ...file,
      bundleId: bundle.bundle_id
    }))
  }))

  const hasUploads = computed(() => bundleIds.value.length > 0)

  const openFilePicker = () => {
    uploadError.value = ''
    fileInputRef.value?.click()
  }

  const openFolderPicker = () => {
    uploadError.value = ''
    folderInputRef.value?.click()
  }

  const uploadSelection = async (fileList) => {
    const files = Array.from(fileList || [])
    if (files.length === 0) {
      return null
    }

    uploading.value = true
    uploadError.value = ''

    try {
      const paths = buildRelativePaths(files)
      const { data } = await uploadAPI.createBundle(files, paths)
      bundles.value = [...bundles.value, data]
      return data
    } catch (error) {
      uploadError.value = extractApiError(error, '上传文件失败')
      throw error
    } finally {
      uploading.value = false
    }
  }

  const handleFileChange = async (event) => {
    try {
      await uploadSelection(event?.target?.files)
    } finally {
      if (event?.target) {
        event.target.value = ''
      }
    }
  }

  const handleFolderChange = async (event) => {
    try {
      await uploadSelection(event?.target?.files)
    } finally {
      if (event?.target) {
        event.target.value = ''
      }
    }
  }

  const removeBundle = (bundleId) => {
    bundles.value = bundles.value.filter((bundle) => bundle.bundle_id !== bundleId)
  }

  const clearBundles = () => {
    bundles.value = []
    uploadError.value = ''
  }

  return {
    bundles,
    bundleIds,
    totalFiles,
    uploadedFiles,
    hasUploads,
    uploading,
    uploadError,
    fileInputRef,
    folderInputRef,
    openFilePicker,
    openFolderPicker,
    handleFileChange,
    handleFolderChange,
    removeBundle,
    clearBundles
  }
}
