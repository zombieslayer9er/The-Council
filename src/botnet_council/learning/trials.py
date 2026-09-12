from collections.abc import Iterable

from botnet_council.experience import ExperienceEpisode


def independent_trials(
    episodes: Iterable[ExperienceEpisode],
) -> tuple[ExperienceEpisode, ...]:
    selected: dict[str, ExperienceEpisode] = {}
    for episode in episodes:
        current = selected.get(episode.equivalence_id)
        if current is None or (
            episode.evidence.decision_timestamp,
            episode.episode_id,
        ) < (
            current.evidence.decision_timestamp,
            current.episode_id,
        ):
            selected[episode.equivalence_id] = episode
    return tuple(
        sorted(
            selected.values(),
            key=lambda item: (item.evidence.decision_timestamp, item.episode_id),
        )
    )
