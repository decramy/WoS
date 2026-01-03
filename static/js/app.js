/**
 * WoS (WSJF on Steroids) - Client-side JavaScript
 * 
 * This module handles:
 * - Theme switching (auto/dark/light) with localStorage persistence
 * - Epic creation form toggle in the overview page
 * - Keyboard shortcuts (Escape to close forms)
 */

document.addEventListener('DOMContentLoaded', function () {
	// =========================================================================
	// Theme Management
	// =========================================================================
	
	/**
	 * Safely get a value from localStorage.
	 * May throw in some privacy modes, so we wrap it.
	 */
	function lsGet(key) {
		try { return localStorage.getItem(key); } catch (e) { return null; }
	}
	
	/**
	 * Safely set a value in localStorage.
	 */
	function lsSet(key, val) {
		try { localStorage.setItem(key, val); return true; } catch (e) { return false; }
	}

	try {
		var saved = lsGet('wos-theme'); // 'auto'|'dark'|'light'|null
		var prefersDarkMQ = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
		var prefersDark = prefersDarkMQ ? prefersDarkMQ.matches : false;

		/**
		 * Apply a theme class to the body element.
		 * @param {string} name - 'dark' or 'light'
		 */
		function setBodyClassFor(name) {
			var body = document.body;
			body.classList.remove('dark', 'light');
			if (name === 'dark') body.classList.add('dark');
			else if (name === 'light') body.classList.add('light');
		}

		/**
		 * Apply a theme and update the toggle button.
		 * @param {string} name - 'auto', 'dark', or 'light'
		 */
		function applyTheme(name) {
			var actual = name;
			if (name === 'auto') {
				actual = (prefersDarkMQ && prefersDarkMQ.matches) ? 'dark' : 'light';
			}
			setBodyClassFor(actual);
			
			// Update toggle button icon and title
			var btn = document.getElementById('theme-toggle');
			if (btn) {
				if (name === 'auto') {
					btn.textContent = 'A';
					btn.title = 'Theme: Auto (follows OS)';
				} else if (name === 'dark') {
					btn.textContent = '🌙';
					btn.title = 'Theme: Dark';
				} else {
					btn.textContent = '☀️';
					btn.title = 'Theme: Light';
				}
			}
		}

		// Initialize theme from saved preference or OS preference
		var initial = 'auto';
		if (saved === 'dark' || saved === 'light' || saved === 'auto') initial = saved;
		else initial = prefersDark ? 'dark' : 'light';
		applyTheme(initial);

		// Theme toggle button: cycles auto -> dark -> light -> auto
		var themeToggle = document.getElementById('theme-toggle');
		if (themeToggle) {
			themeToggle.addEventListener('click', function () {
				var current = lsGet('wos-theme');
				if (!current) {
					current = document.body.classList.contains('dark') ? 'dark' : 'light';
					if (saved === null) current = 'auto';
				}
				var order = ['auto', 'dark', 'light'];
				var idx = order.indexOf(current);
				if (idx === -1) idx = 0;
				var next = order[(idx + 1) % order.length];
				lsSet('wos-theme', next);
				applyTheme(next);
			});
		}
		
		// Listen for OS theme preference changes (when in 'auto' mode)
		if (prefersDarkMQ && typeof prefersDarkMQ.addEventListener === 'function') {
			prefersDarkMQ.addEventListener('change', function () {
				var cur = lsGet('wos-theme') || 'auto';
				if (cur === 'auto') applyTheme('auto');
			});
		}
	} catch (e) {
		// Fallback: basic theme toggle without localStorage
		console.warn('Theme initialization error:', e);
		var themeToggle = document.getElementById('theme-toggle');
		if (themeToggle) {
			themeToggle.addEventListener('click', function () {
				var body = document.body;
				var isDark = body.classList.contains('dark');
				if (isDark) {
					body.classList.remove('dark');
					body.classList.add('light');
					themeToggle.textContent = '☀️';
					themeToggle.title = 'Theme: Light (no storage)';
				} else {
					body.classList.remove('light');
					body.classList.add('dark');
					themeToggle.textContent = '🌙';
					themeToggle.title = 'Theme: Dark (no storage)';
				}
			});
		}
	}
	
	// =========================================================================
	// Epic Creation Form
	// =========================================================================
	
	var toggle = document.getElementById('toggle-epic-form');
	var epicCreate = document.getElementById('epic-create');
	var cancel = document.getElementById('cancel-epic-create');
	
	// Toggle button to show/hide epic creation form
	if (toggle && epicCreate) {
		toggle.addEventListener('click', function () {
			if (epicCreate.style.display === 'none' || epicCreate.style.display === '') {
				epicCreate.style.display = 'block';
				var first = epicCreate.querySelector('input[name="title"]');
				if (first) first.focus();
			} else {
				epicCreate.style.display = 'none';
			}
		});
	}

	// Cancel button hides the form
	if (cancel && epicCreate) {
		cancel.addEventListener('click', function () {
			epicCreate.style.display = 'none';
		});
	}

	// Escape key hides the epic creation form
	document.addEventListener('keydown', function (ev) {
		if (ev.key === 'Escape' && epicCreate && epicCreate.style.display === 'block') {
			epicCreate.style.display = 'none';
		}
	});

	// Auto-open epic form if URL contains #epic-create or ?show_epic_form=1
	try {
		var url = new URL(window.location.href);
		if (url.hash === '#epic-create' || url.searchParams.get('show_epic_form') === '1') {
			if (epicCreate) {
				epicCreate.style.display = 'block';
				var first = epicCreate.querySelector('input[name="title"]');
				if (first) first.focus();
			}
		}
	} catch (e) {
		// Ignore URL parsing errors
	}
});