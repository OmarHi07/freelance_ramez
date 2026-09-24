"""Remove stored image files when their rows are deleted (after commit)."""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from catalog.models import Brand, Category, ProductImage
from core.images import delete_file_on_commit


@receiver(post_delete, sender=ProductImage)
def delete_product_image_files(sender, instance, **kwargs):
    delete_file_on_commit(instance.image)
    delete_file_on_commit(instance.thumbnail)


@receiver(post_delete, sender=Brand)
def delete_brand_files(sender, instance, **kwargs):
    delete_file_on_commit(instance.logo)
    delete_file_on_commit(instance.banner_image)


@receiver(post_delete, sender=Category)
def delete_category_files(sender, instance, **kwargs):
    delete_file_on_commit(instance.image)
