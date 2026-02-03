import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const INACTIVITY_TIMEOUT = 24 * 60 * 60 * 1000 // 24 hours in milliseconds
const CHECK_INTERVAL = 60 * 1000 // Check every minute
const STORAGE_KEY = 'last_activity_time'

export function useActivityTracker() {
  const router = useRouter()
  const authStore = useAuthStore()

  let checkInterval = null

  // Update last activity time
  const updateActivity = () => {
    if (authStore.isAuthenticated) {
      localStorage.setItem(STORAGE_KEY, Date.now().toString())
    }
  }

  // Check if user has been inactive for too long
  const checkInactivity = () => {
    if (!authStore.isAuthenticated) {
      return
    }

    const lastActivity = localStorage.getItem(STORAGE_KEY)
    if (!lastActivity) {
      updateActivity()
      return
    }

    const timeSinceLastActivity = Date.now() - parseInt(lastActivity)

    if (timeSinceLastActivity > INACTIVITY_TIMEOUT) {
      // User has been inactive for more than 24 hours
      console.log('User inactive for 24 hours, logging out...')
      authStore.logout()
      router.push('/login?reason=inactivity')
    }
  }

  // Activity event handlers
  const activityEvents = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click']

  const setupActivityListeners = () => {
    activityEvents.forEach(event => {
      window.addEventListener(event, updateActivity, { passive: true })
    })
  }

  const removeActivityListeners = () => {
    activityEvents.forEach(event => {
      window.removeEventListener(event, updateActivity)
    })
  }

  // Start tracking
  const startTracking = () => {
    if (!authStore.isAuthenticated) {
      return
    }

    // Initialize last activity time
    updateActivity()

    // Setup activity listeners
    setupActivityListeners()

    // Start periodic inactivity check
    checkInterval = setInterval(checkInactivity, CHECK_INTERVAL)

    // Check immediately
    checkInactivity()
  }

  // Stop tracking
  const stopTracking = () => {
    removeActivityListeners()

    if (checkInterval) {
      clearInterval(checkInterval)
      checkInterval = null
    }
  }

  // Setup on mount
  onMounted(() => {
    startTracking()
  })

  // Cleanup on unmount
  onUnmounted(() => {
    stopTracking()
  })

  return {
    updateActivity,
    checkInactivity,
    startTracking,
    stopTracking
  }
}
