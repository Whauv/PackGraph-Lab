window.PackGraphCommunityPage = {
  renderChannels(channels, selectedChannelId, onSelect) {
    const container = document.getElementById("community-channels");
    if (!container) return;
    container.innerHTML = channels.map((channel) => `
      <button type="button" class="row-card community-channel-card${channel.channel_id === selectedChannelId ? " active" : ""}" data-community-channel="${this.escape(channel.channel_id)}">
        <strong>${this.escape(channel.name)}</strong>
        <p>${this.escape(channel.description)}</p>
        <small>${this.escape(channel.post_count)} posts</small>
      </button>
    `).join("");
    container.querySelectorAll("[data-community-channel]").forEach((button) => {
      button.addEventListener("click", () => onSelect(button.dataset.communityChannel));
    });
  },

  renderPosts(posts, selectedPostId, onOpen, onUpvote) {
    const container = document.getElementById("community-feed");
    if (!container) return;
    if (!posts.length) {
      container.innerHTML = `<div class="row-card"><p>No posts yet in this channel. Create one to seed the discussion.</p></div>`;
      return;
    }
    container.innerHTML = posts.map((post) => `
      <article class="row-card community-post-card${post.post_id === selectedPostId ? " active" : ""}">
        <div class="explore-result-top">
          <strong>${this.escape(post.title)}</strong>
          <span class="table-badge">${this.escape(post.channel_id)}</span>
        </div>
        <p>${this.escape(post.body)}</p>
        <small>${this.escape(post.author_name)} | ${this.escape(post.created_at)}</small>
        <div class="tags">
          <span class="tag">${this.escape(post.upvotes)} upvotes</span>
          <span class="tag">${this.escape(post.saves)} saves</span>
          <span class="tag">${this.escape(post.comment_count)} comments</span>
        </div>
        ${(post.related_entities || []).length ? `<div class="tags">${post.related_entities.map((entity) => `<span class="tag">${this.escape(entity.label)}</span>`).join("")}</div>` : ""}
        <div class="row-actions">
          <button type="button" class="mini-action" data-open-post="${this.escape(post.post_id)}">Open discussion</button>
          <button type="button" class="mini-action secondary" data-upvote-post="${this.escape(post.post_id)}">Upvote</button>
        </div>
      </article>
    `).join("");
    container.querySelectorAll("[data-open-post]").forEach((button) => {
      button.addEventListener("click", () => onOpen(button.dataset.openPost));
    });
    container.querySelectorAll("[data-upvote-post]").forEach((button) => {
      button.addEventListener("click", () => onUpvote(button.dataset.upvotePost));
    });
  },

  renderDetail(post) {
    const container = document.getElementById("community-detail");
    if (!container) return;
    if (!post) {
      container.innerHTML = `<div class="detail-card"><p>Open a discussion to review related materials, source references, moderation framing, and replies.</p></div>`;
      return;
    }
    container.innerHTML = `
      <div class="detail-card">
        <h5>${this.escape(post.channel_id)}</h5>
        <h4>${this.escape(post.title)}</h4>
        <p>${this.escape(post.body)}</p>
        <div class="tags">
          <span class="tag">${this.escape(post.upvotes)} upvotes</span>
          <span class="tag">${this.escape(post.saves)} saves</span>
          <span class="tag">${this.escape(post.comment_count)} comments</span>
        </div>
      </div>
      <div class="detail-card">
        <h5>Discussion framing</h5>
        <h4>Related references and moderation context</h4>
        <div class="subsection">
          <div class="subsection-heading">Related entities</div>
          <div class="tags">${(post.related_entities || []).length ? post.related_entities.map((entity) => `<span class="tag">${this.escape(entity.label)}</span>`).join("") : `<span class="tag">None</span>`}</div>
        </div>
        <div class="subsection">
          <div class="subsection-heading">Sources</div>
          <div class="card-list compact-list">${(post.source_refs || []).length ? post.source_refs.map((item) => `<div class="row-card"><strong>${this.escape(item)}</strong></div>`).join("") : `<div class="row-card"><p>No source references attached.</p></div>`}</div>
        </div>
        <div class="subsection">
          <div class="subsection-heading">Moderation note</div>
          <p>${this.escape(post.moderation_note || "Keep the discussion useful and grounded.")}</p>
        </div>
        <div class="subsection">
          <div class="subsection-heading">Replies</div>
          <div class="card-list compact-list">${(post.comments || []).length ? post.comments.map((comment) => `<div class="row-card"><strong>${this.escape(comment.author)}</strong><p>${this.escape(comment.body)}</p><small>${this.escape(comment.created_at)}</small></div>`).join("") : `<div class="row-card"><p>No replies yet.</p></div>`}</div>
        </div>
      </div>`;
  },

  escape(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  },
};
