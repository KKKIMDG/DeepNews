__all__ = ["run_analysis_pipeline"]


def run_analysis_pipeline(*args, **kwargs):
    # Lazy: importing the analysis runner loads the models.
    from .analysis import run_analysis_pipeline as run
    return run(*args, **kwargs)
