import { createApp } from '/assets/vendor/vue.esm-browser.prod.js';
createApp({
  data: () => ({ status: 'loading', message: '', query: '', latitude: '', longitude: '', radius_m: 1500, internet_only: false, consent: false }),
  async mounted() {
    try {
      const [source, preferences] = await Promise.all([fetch('/api/map/source'), fetch('/api/preferences')]);
      if (!source.ok || !preferences.ok) throw new Error('로컬 연결 상태를 확인할 수 없습니다.');
      const state = await source.json();
      this.status = state.status;
      this.message = state.message;
      Object.assign(this, await preferences.json());
    } catch (error) { this.status = 'unavailable'; this.message = error.message; }
  },
  methods: {
    async save() {
      const response = await fetch('/api/preferences', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ radius_m: Number(this.radius_m), internet_only: this.internet_only }) });
      this.message = response.ok ? '반경·인터넷 필터 설정만 저장했습니다. 위치는 저장하지 않습니다.' : '설정을 저장하지 못했습니다.';
    },
    locate() {
      if (this.status !== 'ready' || !this.consent) { this.message = '공급자 연결과 위치 사용 동의가 먼저 필요합니다. 위치를 요청하지 않았습니다.'; return; }
      navigator.geolocation.getCurrentPosition(position => { this.latitude = position.coords.latitude; this.longitude = position.coords.longitude; }, () => { this.message = '위치 권한을 사용할 수 없습니다. 위치를 직접 입력할 수 있습니다.'; });
    },
    async search() {
      if (this.status !== 'ready' || !this.consent) { this.message = '실제 지도·장소 공급자가 미설정입니다. 가짜 장소 결과를 표시하지 않습니다.'; return; }
      const response = await fetch('/api/map/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ latitude: Number(this.latitude), longitude: Number(this.longitude), query: this.query, radius_m: Number(this.radius_m), internet_only: this.internet_only, external_consent: this.consent }) });
      this.message = response.ok ? '데이터 연결과 검토가 완료된 구현이 필요합니다.' : (await response.json()).error.message;
    }
  },
  template: `<div><header><h1>카공지도</h1><p>공부·작업할 카페를 찾는 지도</p></header><p role="status">{{ message }}</p><section aria-label="지도 데이터 연결 상태"><h2>실제 지도·장소 연결 대기</h2><p>현재 지도와 카페 데이터가 없습니다. 공급자·무료 자격·출처 표시와 위치 동의 경로가 확정돼야 검색·추천할 수 있습니다.</p><p>이 화면은 카공지도 완성 결과가 아닙니다.</p></section><form @submit.prevent="search"><label>지역·카페 검색<input v-model="query" maxlength="120" placeholder="지역 또는 카페 이름"></label><div class="coordinates"><label>위도<input v-model="latitude" type="number" step="any" min="-90" max="90"></label><label>경도<input v-model="longitude" type="number" step="any" min="-180" max="180"></label></div><label><input v-model="consent" type="checkbox">위치 사용·외부 전송 조건을 먼저 확인하겠습니다(현재 전송 없음)</label><button type="button" @click="locate" :disabled="status !== 'ready' || !consent">내 위치 사용</button><button :disabled="status !== 'ready' || !consent">카페 검색</button></form><form @submit.prevent="save"><h2>로컬 검색 설정</h2><label>검색 반경(m)<input v-model="radius_m" type="number" min="100" max="5000" required></label><label><input v-model="internet_only" type="checkbox">출처에 인터넷 정보가 있는 카페만(연결 후 사용)</label><button>설정 저장</button><p>좌표·검색어는 저장하지 않습니다. 조용함·콘센트·장시간 이용 가능 여부는 데이터만으로 보증하지 않습니다.</p></form></div>`
}).mount('#app');
