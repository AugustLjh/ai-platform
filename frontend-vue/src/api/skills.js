import api from './axios'

export const skillsAPI = {
  listSkills() {
    return api.get('/api/v1/skills')
  },

  getSkill(skillId) {
    return api.get(`/api/v1/skills/${skillId}`)
  },

  syncSkills() {
    return api.post('/api/v1/skills/sync')
  },

  updateAgentSkills(agentId, skillIds = []) {
    return api.put(`/api/v1/agents/${agentId}/skills`, {
      skill_ids: skillIds
    })
  }
}
